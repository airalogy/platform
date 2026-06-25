import os
from base64 import b64decode, b64encode

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


def aes_encrypt(data, key, iv=None):
    # data: utf-8编码的字符串
    # key: hex编码的字符串
    # AES 要求密钥和块大小匹配，AES-256 需要32字节密钥
    key = bytes.fromhex(key)
    data = data.encode("utf-8")

    # 生成随机的初始化向量
    if iv is None:
        iv = os.urandom(AES.block_size)
    else:
        iv = bytes.fromhex(iv)
    # print("iv:", iv.hex())

    # 创建加密器，使用CBC模式
    cipher = AES.new(key, AES.MODE_CBC, iv)

    # 填充数据以满足AES加密数据块大小的要求
    padded_data = pad(data, AES.block_size)

    # 加密数据
    encrypted = cipher.encrypt(padded_data)

    # 结合初始化向量和加密的数据，并进行base64编码
    encrypted_data_with_iv = iv + encrypted
    encrypted_data_base64 = b64encode(encrypted_data_with_iv)

    return encrypted_data_base64.decode("utf-8")


def aes_decrypt(encrypted_data_base64, key):
    # 将base64编码的数据解码
    encrypted_data_with_iv = b64decode(encrypted_data_base64)

    # 提取初始化向量和加密的数据
    iv = encrypted_data_with_iv[: AES.block_size]
    encrypted_data = encrypted_data_with_iv[AES.block_size :]

    # AES 解密
    cipher = AES.new(bytes.fromhex(key), AES.MODE_CBC, iv)
    padded_data = cipher.decrypt(encrypted_data)

    # 移除填充
    data = unpad(padded_data, AES.block_size)

    return data.decode("utf-8")
