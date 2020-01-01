FROM python:3.7-alpine

RUN apk add --no-cache tzdata

COPY . /imap2smtp

WORKDIR /imap2smtp

RUN pip install -r requirements.txt

ENV PYTHONPATH /imap2smtp

ENTRYPOINT ["python" ,"-u", "docker/entrypoint.py"]
