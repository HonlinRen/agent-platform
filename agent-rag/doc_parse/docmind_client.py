# -*- coding: utf-8 -*-
import os

from alibabacloud_credentials.client import Client as CredClient
from alibabacloud_docmind_api20220711.client import Client as docmind_api20220711Client
from alibabacloud_tea_openapi import models as open_api_models

DOCMIND_ENDPOINT = os.environ.get(
    "DOCMIND_ENDPOINT", "docmind-api.cn-hangzhou.aliyuncs.com"
)


def create_client() -> docmind_api20220711Client:
    cred = CredClient()
    credential = cred.get_credential()
    config = open_api_models.Config(
        access_key_id=credential.get_access_key_id(),
        access_key_secret=credential.get_access_key_secret(),
    )
    config.endpoint = DOCMIND_ENDPOINT
    return docmind_api20220711Client(config)
