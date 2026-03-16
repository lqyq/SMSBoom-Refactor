# encoding=utf8
# 请求的方法
import httpx
from httpx import Limits
from typing import Union, List, Optional
import asyncio

from utils import default_header_user_agent
from utils.models import API
from utils.log import logger

# 兼容旧代码：handle_api.py 会从这里 import default_header
# 同时 asyncReqs() 也会使用该变量作为默认 headers
default_header = default_header_user_agent()

def _clone_api(src: API) -> API:
    """避免在多手机号场景下修改同一个 API 对象，导致后续手机号无法替换。"""
    # pydantic v2: model_copy；v1: copy
    if hasattr(src, 'model_copy'):
        return src.model_copy(deep=True)  # type: ignore[attr-defined]
    return src.copy(deep=True)

def _make_sync_client(proxy: Optional[dict] = None) -> httpx.Client:
    """兼容不同 httpx 版本的代理参数（proxies -> proxy）。"""
    kwargs = {
        'headers': default_header_user_agent(),
        'verify': False,
    }
    if proxy:
        # 旧版 httpx: proxies=...
        try:
            return httpx.Client(**kwargs, proxies=proxy)  # type: ignore[call-arg]
        except TypeError:
            # 新版 httpx: proxy=...
            proxy_url = None
            if isinstance(proxy, dict):
                proxy_url = proxy.get('all://')
            return httpx.Client(**kwargs, proxy=proxy_url)
    return httpx.Client(**kwargs)

def reqAPI(api: API, client: Union[httpx.Client, httpx.AsyncClient]):
    """同步/异步统一请求。

    - 对 httpx.Client 返回 httpx.Response
    - 对 httpx.AsyncClient 返回 awaitable (Coroutine)

    由于两者返回类型不同，这里不强行标注返回类型，避免类型误导。
    """
    if isinstance(api.data, dict):
        return client.request(method=api.method, json=api.data,
                              headers=api.header, url=api.url, timeout=10)
    return client.request(method=api.method, data=api.data,
                          headers=api.header, url=api.url, timeout=10)

def reqFuncByProxy(api: Union[API, str], phone: Union[tuple, str], proxy: dict) -> bool:

    """通过代理请求接口方法"""
    # 多手机号支持
    if isinstance(phone, tuple):
        phone_lst = [str(_) for _ in phone]
    else:
        phone_lst = [str(phone)]

    ok = False
    with _make_sync_client(proxy) as client:
        for ph in phone_lst:
            try:
                if isinstance(api, API):
                    api_ = _clone_api(api).handle_API(ph)
                    resp = reqAPI(api_, client)
                    logger.info(f"{ph} | {api_.desc} - {resp.text.strip()[:50]}")
                else:
                    api_url = api.replace("[phone]", ph).replace(" ", "").replace('\n', '').replace('\r', '')
                    resp = client.get(url=api_url, headers=default_header_user_agent())
                    logger.info(f"{ph} | GETAPI接口-{resp.text[:50]}")
                ok = True
            except httpx.HTTPError as why:
                logger.error(f"{ph} | 请求失败 {why}")
                continue

    return ok

def reqFunc(api: Union[API, str], phone: Union[tuple, str]) -> bool:

    """请求接口方法"""
    # 多手机号支持
    if isinstance(phone, tuple):
        phone_lst = [str(_) for _ in phone]
    else:
        phone_lst = [str(phone)]

    ok = False
    with _make_sync_client() as client:
        for ph in phone_lst:
            try:
                if isinstance(api, API):
                    api_ = _clone_api(api).handle_API(ph)
                    resp = reqAPI(api_, client)
                    logger.info(f"{ph} | {api_.desc} - {resp.text.strip()[:50]}")
                else:
                    api_url = api.replace("[phone]", ph).replace(" ", "").replace('\n', '').replace('\r', '')
                    resp = client.get(url=api_url, headers=default_header_user_agent())
                    logger.info(f"{ph} | GETAPI接口-{resp.text[:50]}")
                ok = True
            except httpx.HTTPError as why:
                logger.error(f"{ph} | 请求失败 {why}")
                continue

    return ok

async def asyncReqs(src: Union[API, str], phone: Union[tuple, str], semaphore):
    """异步请求方法

    :param:
    :return:

    """
    # 多手机号支持
    if isinstance(phone, tuple):
        phone_lst = [_ for _ in phone]
    else:
        phone_lst = [phone]
    async with semaphore:
        async with httpx.AsyncClient(
            limits=Limits(max_connections=1000,
                          max_keepalive_connections=2000),
            headers=default_header,
            verify=False,
            timeout=99999
        ) as c:

            for ph in phone_lst:
                try:
                    if isinstance(src, API):
                        src = src.handle_API(ph)
                        r = await reqAPI(src, c)
                    else:
                        # 利用元组传参安全因为元组不可修改
                        s = (src.replace(" ", "").replace("\n", "").replace("\t", "").replace(
                            "&amp;", "").replace('\n', '').replace('\r', ''),)
                        r = await c.get(*s)
                    return r
                except httpx.HTTPError as why:
                    logger.error(f"异步请求失败{type(why)}")
                    # logger.error(f"异步请求失败{why}")
                    # import aiofiles
                    # async with aiofiles.open("error.txt","a",encoding="utf-8") as f:
                    #     await f.write(f"{str(s[0]) if str(s[0]) else str(src)}\n")
                except TypeError:
                    logger.error("类型错误")
                except Exception as wy:
                    logger.exception(f"异步失败{wy}")

def callback(result):
    """异步回调函数"""
    log = result.result()
    if log is not None:
        logger.info(f"请求结果:{log.text[:50]}")

async def runAsync(apis: List[Union[API,str]], phone: Union[tuple, str]):
    
    tasks = []

    for api in apis:
        semaphore = asyncio.Semaphore(999999)
        task = asyncio.ensure_future(asyncReqs(api, phone, semaphore))
        task.add_done_callback(callback)
        tasks.append(task)

    await asyncio.gather(
        *tasks
    )
