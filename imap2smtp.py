#!/usr/bin/env python3
# Author: FL42

"""
See README.md
"""

import argparse
import email
import imaplib
import logging
import signal
import smtplib
import threading
from datetime import datetime
from random import random
from sys import exit as sys_exit
from time import sleep

import yaml

version = "1.0.0"


class Imap2Smtp(threading.Thread):
    """
    See module docstring
    """

    def __init__(self, config_path):

        # Init from mother class
        threading.Thread.__init__(self)

        # Set up logger
        self.log = logging.getLogger(config_path)
        self.log.setLevel(logging.INFO)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(
            logging.Formatter(
                fmt="[{}] %(asctime)s:%(levelname)s:%(message)s".format(
                    config_path
                ),
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        )
        self.log.addHandler(stream_handler)

        # Initialize vars
        self.config_path = config_path
        self.config = None
        # exit event: exit when set
        self.exit_event = threading.Event()
        self.imap = None
        self.smtp = None

    def run(self):
        """
        Run method (see threading module)
        """

        # Load config
        if self.config_path is not None:
            with open(self.config_path, 'rt') as config_file:
                self.config = yaml.safe_load(config_file)
        else:
            raise Exception('Path to config is required')

        # Set up loglevel
        self.log.setLevel(
            logging.DEBUG if self.config['common'].get('debug', False)
            else logging.INFO
        )

        config_sleep = self.config['common'].get('sleep', None)
        sleep_var_pct = self.config['common'].get('sleep_var_pct', None)
        while not self.exit_event.is_set():

            success = self.forward(
                imap_config=self.config['imap'],
                smtp_config=self.config['smtp']
            )

            if config_sleep is None:
                sys_exit(not success)  # 0 on success

            # Try again after 10s if case of error
            if not success:
                sleep(10)
                continue

            if config_sleep == 'auto':
                hour = datetime.now().hour
                if 7 <= hour <= 20:
                    sleep_time = 300
                else:
                    sleep_time = 1800
            else:
                sleep_time = config_sleep

            if sleep_var_pct:
                random_delta = \
                    (2*random() - 1.0) * (sleep_var_pct / 100) * sleep_time
                self.log.debug(
                    "Adding %.2f seconds for randomness",
                    random_delta
                )
                sleep_time += random_delta

            self.log.debug("Waiting %.2f seconds...", sleep_time)
            self.exit_event.wait(sleep_time)
        self.log.info("Exited")

    def forward(self, imap_config, smtp_config):
        """
        Get emails from IMAP server and forward them using smtp server.
        Return bool indicating success.
        """

        self.imap = self.imap_login(imap_config)
        if self.imap is not None:
            self.log.debug("IMAP logged")
        else:
            self.log.error("IMAP failed")
            return False
        self.smtp = None  # SMTP will be open if there are messages to forward

        mailbox = imap_config.get('mailbox', 'INBOX')
        message_list = self.get_message_list(mailbox)
        if message_list is None:
            self.log.error("Failed to get list of message")
            return False

        counter_success = 0
        counter_failure = 0
        for msg_id in message_list:
            # Open connection to SMTP server (first time)
            if self.smtp is None:
                self.smtp = self.setup_smtp(smtp_config)
                if self.smtp is not None:
                    self.log.debug("SMTP logged")
                else:
                    self.log.error("SMTP failed")
                    return False

            msg = self.fetch_message(msg_id)
            if msg is None:
                self.log.error(
                    "Error while fetching message %s, continue",
                    msg_id
                )
                continue

            self.log.debug(
                "msg: id: %s, from: %s, to: %s, subject: %s, date: %s",
                msg_id,
                msg['From'],
                msg['To'],
                msg.get('Subject', '(No subject)'),
                msg['Date']
            )

            message_forwarded, smtp_error_code = self.send_message(
                msg=msg,
                to_addr=self.config['smtp']['forward_address']
            )

            if message_forwarded:
                counter_success += 1
                self.postprocess_message(
                    msg_id,
                    imap_config.get('move_to_mailbox', None),
                    imap_config.get('mark_as_seen', False),
                )
            else:
                counter_failure += 1
                self.log.error("Failed to forward message %s", msg_id)
                if not smtp_error_code or smtp_error_code < 500:
                    self.log.error(
                        "SMTP error code: %d => temporary error",
                        smtp_error_code
                    )
                else:
                    self.log.error(
                        "SMTP error code: %d => permanent error",
                        smtp_error_code
                    )
                    self.postprocess_message(
                        msg_id,
                        destination_mailbox=imap_config.get(
                            'move_to_mailbox_failed',
                            None
                        ),
                        mark_as_seen=False,
                    )

        self.imap.expunge()
        self.close()
        self.log.info(
            "stats: to=%s forward_success=%d forward_failure=%d",
            self.config['smtp']['forward_address'],
            counter_success,
            counter_failure
        )
        return True

    def imap_login(self, imap_config):
        """
        Set up connexion to IMAP server

        Parameter:
        imap_config:
            - host: (str) IMAP server hostname
            - port: (int) Default to 143 if ssl if false,
                          993 if ssl is true
            - ssl: (bool) Use SSL
            - user: (str) IMAP username
            - password: (str) IMAP password

        Return:
        (imaplib imap object)
        or None on error
        """
        try:
            if not imap_config['ssl']:
                imap = imaplib.IMAP4(
                    imap_config['host'],
                    imap_config.get('port', 143)
                )
            else:
                imap = imaplib.IMAP4_SSL(
                    imap_config['host'],
                    imap_config.get('port', 993)
                )

            self.log.debug(
                "Connexion opened to %s (%s)",
                imap_config['host'],
                "SSL" if imap_config['ssl'] else "PLAIN"
            )

            typ, data = imap.login(
                imap_config['user'],
                imap_config['password']
            )
            if typ == 'OK':
                self.log.debug("IMAP login has succeeded")
            else:
                self.log.error("Failed to log in: %s", str(data))
                return None

            return imap

        except (imaplib.IMAP4.error, OSError) as imap_exception:
            self.log.exception(imap_exception)
            return None

    def get_message_list(self, mailbox):
        """
        Get list of message ID in 'mailbox'

        Parameter:
        mailbox: (str) Mailbox to fetch (e.g. 'INBOX')

        Return: (list of str) List of message ID in mailbox
                or None on error
        """

        try:
            typ, data = self.imap.select(mailbox)
            if typ == 'OK':
                self.log.debug("IMAP select '%s' succeeded", mailbox)
            else:
                self.log.error("Failed to select '%s': %s", mailbox, data)
                return None

            typ, data = self.imap.search(None, 'ALL')
            if typ == 'OK':
                self.log.debug("IMAP search on 'ALL' succeeded")
            else:
                self.log.error("Failed to search on 'ALL': %s", str(data))
                return None

            return data[0].split()

        except (imaplib.IMAP4.error, OSError) as imap_exception:
            self.log.exception(imap_exception)
            return None

    def fetch_message(self, msg_id):
        """
        Fetch message defined by msg_id

        Parameter:
        msg_id: (str) ID of the message to get (index in IMAP server)

        Return:
        (email.message.Message object) fetched Message
        or None on error
        """

        try:
            typ, data = self.imap.fetch(msg_id, '(RFC822)')
            if typ == 'OK':
                self.log.debug("Message %s fetched", msg_id)
            else:
                self.log.error("Failed to fetch message %s", msg_id)
                return None

            return email.message_from_bytes(data[0][1])

        except (imaplib.IMAP4.error, OSError) as imap_exception:
            self.log.exception(imap_exception)
            return None

    def postprocess_message(self, msg_id, destination_mailbox, mark_as_seen):
        """
        Post process 'msg_id'

        Parameters:
        msg_id: (str) ID of the message (IMAP ID)
        destination_mailbox: (str) Name of the destination mailbox
                                   or 'None' to do nothing
        mark_as_seen: (bool) Mark the email as seen

        Return:
        True on success, else False
        """
        try:
            if mark_as_seen:
                self.imap.store(msg_id, '+FLAGS', '\\Seen')
                self.log.debug("Message marked as seen")

            if destination_mailbox is not None:
                # Use COPY and DELETE as not all servers support MOVE
                self.imap.copy(msg_id, destination_mailbox)
                self.imap.store(msg_id, '+FLAGS', '\\Deleted')
                # Expunge will be done later
                self.log.debug("Message moved to %s", destination_mailbox)

            return True

        except (imaplib.IMAP4.error, OSError) as imap_exception:
            self.log.exception(imap_exception)
            return False

    def setup_smtp(self, smtp_config):
        """
        Set up connexion to SMTP server

        Parameters:
        smtp_config (dict):
            host: (str) smtp host server
            port: (int) smtp port (default to 587)
            starttls: (bool) enable STARTTLS (default to True)
            user: (str or None) smtp user (or None)
            password: (str or None) smtp password (or None)

        Return:
        (smtplib.SMTP) smtp object
        or None on error
        """

        try:
            smtp = smtplib.SMTP(
                host=smtp_config['host'],
                port=smtp_config.get('port', 587)
            )
            self.log.debug("Connexion opened to %s", smtp_config['host'])

            if smtp_config.get('starttls', True):
                smtp.starttls()
                self.log.debug("STARTTLS has succeeded")
            else:
                self.log.debug("SMTP is in PLAIN (no STARTTLS)")

            smtp_user = smtp_config.get('user', None)
            smtp_password = smtp_config.get('password', None)
            if smtp_user is not None and smtp_password is not None:
                smtp.login(smtp_user, smtp_password)
                self.log.debug("SMTP login has succeeded")
            else:
                self.log.debug("No login given for SMTP")

            return smtp

        except (smtplib.SMTPResponseException, OSError) as smtp_exception:
            self.log.exception(smtp_exception)
            return None

    def send_message(self, msg, to_addr):
        """
        Send 'msg' to 'to_addr'

        Parameters:
        msg: (email.message.Message object) Message to send
        to_addr: (str) destination address

        Return:
        (bool) Message sent, (int) error code or None
        """

        try:
            self.smtp.send_message(
                msg,
                to_addrs=to_addr
            )
            self.log.debug("Message sent")
        except smtplib.SMTPRecipientsRefused as smtp_exception:
            self.log.exception(smtp_exception)
            return False, smtp_exception.recipients[to_addr][0]
        except smtplib.SMTPResponseException as smtp_exception:
            self.log.exception(smtp_exception)
            return False, smtp_exception.smtp_code
        except smtplib.SMTPException as smtp_exception:
            self.log.exception(smtp_exception)
        except (OSError, IOError) as os_exception:
            self.log.exception(os_exception)
        return True, None

    def close(self):
        """
        Close IMAP and SMTP connexions
        """
        self.imap.close()
        self.imap.logout()
        self.log.debug("IMAP closed")
        if self.smtp is not None:
            self.smtp.quit()
            self.log.debug("SMTP closed")


if __name__ == '__main__':

    # Parse arguments
    parser = argparse.ArgumentParser(description="IMAP to SMTP forwarder")
    parser.add_argument(
        '-c', '--config',
        help="Path to config file"
    )
    args = parser.parse_args()

    # Print version at startup
    print("IMAP to SMTP forwarder V{}".format(version))

    # Handle signal
    def exit_gracefully(sigcode, _frame):
        """
        Exit immediately gracefully
        """
        imap2smtp.log.info("Signal %d received", sigcode)
        imap2smtp.log.info("Exiting gracefully now...")
        imap2smtp.exit_event.set()
        sys_exit(0)
    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGTERM, exit_gracefully)

    # Start Imap2Smtp thread
    imap2smtp = Imap2Smtp(
        config_path=args.config
    )
    imap2smtp.start()

    while True:
        if not imap2smtp.is_alive():
            break
        sleep(600)
    sys_exit(1)
