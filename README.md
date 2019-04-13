# IMAP to SMTP forwarder

[![Build Status](https://travis-ci.org/selfhosting-tools/imap2smtp.svg?branch=master)](https://travis-ci.org/selfhosting-tools/imap2smtp)

This tools helps to gather emails from various IMAP servers to one mailbox.
It uses an SMTP server to send gathered emails to one mailbox.

'From' header of emails won't be modified (transparent forwarding).
Pay attention that transparent forwarding breaks SPF check.

This is especially useful if your provider prevents you from forwarding your emails.

This tool uses almost only built-in libraries (except PyYAML) and should works on any Python 3.4+

Feel free to open issue or PR.

TODO:
- Unittest-based tests (see 'tests' branch for progress).

Author: FL42


## Command-line usage
Install dependencies using:
```bash
pip3 install --user -r requirements.txt
```
Run the program:
```bash
python3 imap2smtp.py -c config.yaml
```


## Docker usage
As it is security sensitive (e.g. IMAP/SMTP passwords), I do not recommend to use an image from Docker Hub.
Building is really simple and should be done locally (ideally after checking GPG commit signature).
```bash
git clone --depth 1 https://github.com/selfhosting-tools/imap2smtp.git
git -C imap2smtp verify-commit HEAD
cp imap2smtp/docker/docker-compose.yaml .
docker-compose build
```
Patch `docker-compose.yaml` to your own path for config directory if needed (default to ./config).  
Put your config files in your config directory.
You should set strict permissions to your config files (i.e. owned by root and chmod 600).  
All config files in the config directory will be run in parallel.  
Finally start the container:
```bash
docker-compose up -d
```


## Configuration file format
See `example.yaml`.  
All sections are required (even if there are empty).

### common section
- debug: (bool) Enable debugging mode (more verbose). Default to `false`.
- sleep: In case of error a new attempt will be made 10s after indefinitely (except for one-time run)
  - not present: exit immediately after one run (could be useful to use with cron)
  Exit code is 1 if forwarding failed, else 0.
  - (str) 'auto': wait 5 mins during the day (7 am to 9 pm) and 30 mins during the night between 2 checks for new emails to forward
  - (int) constant time to sleep between 2 checks for new emails to forward

### imap section
- host: (str) hostname of the IMAP server
- port: (int) Default to 143 if ssl is false, 993 if ssl is true
- ssl: (bool) Enable SSL
- user: (str) IMAP user
- password: (str) IMAP password
- mailbox: (str) mailbox name to check for emails to forward. Default to `'INBOX'`.
- mark_as_seen: (bool) mark forwarded emails as seen. Default to `false`.
- move_to_mailbox: (str) move forwarded emails to different mailbox (on the same IMAP server) after forwarding (e.g. 'Fowarded emails'). Remove or set to `null` to disable. Default to `null`

### smtp section
- host: (str) hostname of the SMTP server
- port: (int) port of the SMTP server. Default to 587.
- starttls: (bool) Enable STARTTLS. Default to `true`
- user: (str) SMTP user (remove or set to `null` to disable authentification)
- password: (str) SMTP password (remove or set to `null` to disable authentification)
- forward_address: (str) address to forward emails
