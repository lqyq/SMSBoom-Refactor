#!/usr/bin/python python3
# coding=utf-8
from . import main
from flask import redirect, url_for, request, abort


@main.app_errorhandler(404)
def page_not_found(e):
    """注册应用全局错误处理
    
    注意：只对HTML页面请求进行重定向，对静态资源请求（JS、CSS、图片等）
    返回标准404响应，避免导致 ERR_INVALID_HTTP_RESPONSE 错误
    """
    # 获取请求的路径
    path = request.path.lower()
    
    # 静态资源扩展名列表
    static_extensions = ('.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.ico', 
                         '.svg', '.woff', '.woff2', '.ttf', '.eot', '.map',
                         '.json', '.xml', '.txt', '.pdf', '.zip')
    
    # 如果是静态资源请求，返回标准404响应
    if path.endswith(static_extensions) or '/static/' in path:
        return "Not Found", 404
    
    # 检查 Accept 头，如果客户端不接受 HTML，返回标准404
    accept = request.headers.get('Accept', '')
    if 'text/html' not in accept and '*/*' not in accept:
        return "Not Found", 404
    
    print("404 - redirecting to index")
    return redirect(url_for('main.index'))


@main.app_errorhandler(401)
def authfail(e):
    return redirect('/static/401.jpg')