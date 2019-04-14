FROM python:3.7-alpine

RUN apk add --no-cache git curl gnupg

RUN cd / && git clone --depth 1 https://github.com/selfhosting-tools/imap2smtp.git

WORKDIR /imap2smtp

RUN TRUSTED_GPG_KEYS="CA2B146D7407C0932B96AA8756CD3255CE0673F6" && \
    VALID_SIG=0 && \
    for KEY_FP in $TRUSTED_GPG_KEYS; do \
        curl -s https://raw.githubusercontent.com/selfhosting-tools/master-keys/master/$KEY_FP.asc | gpg --import && \
        [ "$KEY_FP" == "$(git verify-commit --raw HEAD 2>&1 | grep "^\[GNUPG:\] VALIDSIG" | awk '{print $12}')" ] && VALID_SIG=1; \
    done && \
    [ $VALID_SIG -eq 1 ] && exit 0 || exit 1

RUN pip install -r requirements.txt

ENV PYTHONPATH /imap2smtp
ENTRYPOINT ["python" ,"-u", "docker/entrypoint.py"]
