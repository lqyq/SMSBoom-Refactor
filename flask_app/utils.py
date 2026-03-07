# encoding=utf8
import httpx
from .model import API, default_header_user_agent as default_header
def test_resq(api: API, phone) -> httpx.Response:
    """测试 API 返回响应
    :param api: API model
    :param phone: 手机号
    :return: httpx 请求对象.
    """
    context = httpx.create_ssl_context()
    context.set_ciphers('ALL')
    api = api.handle_API(phone)
    api.header.update({'Connection': 'keep-alive',
                    'Accept': '*/*',
                    # 'User-Agent': 'ironLGMI/3.7.4 (iPhone; iOS 15.4.1; Scale/3.00)',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0',
                    'Accept-Language': 'zh-Hans-CN;q=1',
                    'Accept-Encoding': 'gzip, deflate'
    })
    with httpx.Client(headers=default_header(), timeout=8, verify=False) as client:
        # 这个判断没意义.....但是我不知道怎么优化...
        # https://stackoverflow.com/questions/26685248/difference-between-data-and-json-parameters-in-python-requests-package
        # Todo: json 和 data 表单发送的问题,有些服务器不能解释 json,只能接受表单
        # sol: 1. 添加额外字段判断...
        if not isinstance(api.data, dict):
            print("data")
            # api.header['Content-Type'] = api.header.get('Content-Type','application/x-www-form-urlencoded')
            resp = client.request(method=api.method, headers=api.header,
                                  url=api.url, data=api.data)
        else:
            print('json')
            # api.header['Content-Type'] = api.header.get('Content-Type','application/json')
            resp = client.request(method=api.method, headers=api.header,
                                  url=api.url, json=api.data)

    return resp


if __name__ == '__main__':
    pass
