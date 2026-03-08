# encoding=utf8
# flask app views
import os
from . import main
import json
from ..model import Apis, API
from ..utils import test_resq
from .. import logger
import httpx
from flask_app import db
from flask import request, jsonify, Response, render_template, current_app
from datetime import datetime
import concurrent.futures
import threading

# 批量测试进度跟踪
test_progress = {
    'running': False,
    'total': 0,
    'completed': 0,
    'success': 0,
    'failed': 0,
    'current_api': '',
    'results': [] # 存储最近测试的结果 {id, status}
}
progress_lock = threading.Lock()


@main.route("/", methods=['GET', 'POST'])
def index():
    return "index"


@main.route("/testapi/", methods=['GET', 'POST'])
def testapi():
    try:
        req = request.json
        api = API(**req)
        resp = test_resq(api, phone=req.get('phone'))
        print(resp.text)
        return jsonify({"status": 0, "resp": f"{resp.text}"})
    except httpx.HTTPError as why:
        return jsonify({"status": 1, "resp": f"HTTP请求错误:{why}"})
    except Exception as why:
        logger.exception(why)
        return jsonify({"status": 1, "resp": f"其他错误:{why}"})


@main.route("/testapi/<int:api_id>/", methods=['POST'])
def testapi_by_id(api_id):
    """根据 API ID 测试接口，并更新数据库状态"""
    try:
        req = request.json
        phone = req.get('phone')
        
        # 从数据库获取 API
        api_record = Apis.query.get(api_id)
        if not api_record:
            return jsonify({"status": 1, "resp": "API 不存在"})
        
        # 构建 API 对象
        api_data = {
            "desc": api_record.desc,
            "url": api_record.url,
            "method": api_record.method,
            "header": api_record.header or "",
            "data": api_record.data or ""
        }
        api = API(**api_data)
        
        # 测试请求
        resp = test_resq(api, phone=phone)
        
        # 更新数据库状态
        api_record.last_test_time = datetime.now()
        api_record.last_test_response = resp.text[:10000] if resp.text else ""  # 保存前10000字符
        
        # 判断成功/失败：状态码 2xx 为成功
        logger.info(f"Test result for API {api_id}: Status Code {resp.status_code}")
        if 200 <= resp.status_code < 300:
            api_record.status = "success"
            try:
                db.session.commit()
                logger.info(f"Successfully saved status 'success' for API {api_id}")
            except Exception as e:
                logger.error(f"Database commit failed for API {api_id} (success path): {e}")
                db.session.rollback()
                raise e

            return jsonify({
                "status": 0,
                "resp": resp.text[:10000], # 返回更多内容供前端展示
                "api_status": "success",
                "status_code": resp.status_code
            })
        else:
            api_record.status = "failed"
            try:
                db.session.commit()
                logger.info(f"Successfully saved status 'failed' for API {api_id}")
            except Exception as e:
                logger.error(f"Database commit failed for API {api_id} (failed path): {e}")
                db.session.rollback()
                raise e

            return jsonify({
                "status": 1,
                "resp": f"HTTP {resp.status_code}: {resp.text[:10000]}",
                "api_status": "failed",
                "status_code": resp.status_code
            })
            
    except httpx.HTTPError as why:
        # 更新为失败状态
        api_record = Apis.query.get(api_id)
        if api_record:
            api_record.status = "failed"
            api_record.last_test_time = datetime.now()
            api_record.last_test_response = str(why)[:2000]
            try:
                db.session.commit()
                logger.info(f"Successfully saved status 'failed' (HTTP Error) for API {api_id}")
            except Exception as e:
                logger.error(f"Database commit failed for API {api_id} (HTTP Error path): {e}")
                db.session.rollback()
        return jsonify({"status": 1, "resp": f"HTTP请求错误:{why}", "api_status": "failed"})
    except Exception as why:
        logger.exception(why)
        api_record = Apis.query.get(api_id)
        if api_record:
            api_record.status = "failed"
            api_record.last_test_time = datetime.now()
            api_record.last_test_response = str(why)[:2000]
            try:
                db.session.commit()
                logger.info(f"Successfully saved status 'failed' (Exception) for API {api_id}")
            except Exception as e:
                logger.error(f"Database commit failed for API {api_id} (Exception path): {e}")
                db.session.rollback()
        return jsonify({"status": 1, "resp": f"其他错误:{why}", "api_status": "failed"})


@main.route("/batch_test/", methods=['POST'])
def batch_test():
    """启动批量测试所有接口"""
    global test_progress
    
    with progress_lock:
        if test_progress['running']:
            return jsonify({"status": 1, "resp": "批量测试正在进行中"})
    
    req = request.json
    phone = req.get('phone')
    filter_status = req.get('filter_status')  # 可选：只测试特定状态的接口
    ids = req.get('ids')  # 可选：只测试指定 ID 的接口
    
    if not phone:
        return jsonify({"status": 1, "resp": "请提供测试手机号"})
    
    # 查询要测试的接口
    query = Apis.query
    
    if ids and len(ids) > 0:
        query = query.filter(Apis.id.in_(ids))
    elif filter_status:
        query = query.filter(Apis.status == filter_status)
        
    apis = query.all()
    
    if not apis:
        return jsonify({"status": 1, "resp": "没有找到要测试的接口"})
    
    # 初始化进度
    with progress_lock:
        test_progress = {
            'running': True,
            'total': len(apis),
            'completed': 0,
            'success': 0,
            'failed': 0,
            'current_api': '',
            'results': []
        }
    
    # 获取当前应用实例
    from flask import current_app
    app = current_app._get_current_object()
    
    # 创建新线程，将 app 传递进去
    def run_with_context():
        with app.app_context():
            run_batch_test_inner()
    
    def run_batch_test_inner():
        global test_progress
        
        for api_record_orig in apis:
            # 在循环内部重新查询对象，确保它绑定到当前线程的 session
            api_record = Apis.query.get(api_record_orig.id)
            if not api_record:
                continue

            with progress_lock:
                if not test_progress['running']:
                    break
                test_progress['current_api'] = api_record.desc
            
            try:
                api_data = {
                    "desc": api_record.desc,
                    "url": api_record.url,
                    "method": api_record.method,
                    "header": api_record.header or "",
                    "data": api_record.data or ""
                }
                api = API(**api_data)
                resp = test_resq(api, phone=phone)
                
                api_record.last_test_time = datetime.now()
                api_record.last_test_response = resp.text[:10000] if resp.text else ""
                
                if 200 <= resp.status_code < 300:
                    api_record.status = "success"
                    with progress_lock:
                        test_progress['success'] += 1
                        test_progress['results'].append({
                            'id': api_record.id,
                            'status': 'success',
                            'response': resp.text[:2000] if resp.text else ""
                        })
                else:
                    api_record.status = "failed"
                    with progress_lock:
                        test_progress['failed'] += 1
                        test_progress['results'].append({
                            'id': api_record.id,
                            'status': 'failed',
                            'response': f"HTTP {resp.status_code}: {resp.text[:2000]}" if resp.text else f"HTTP {resp.status_code}"
                        })
                        
            except Exception as e:
                api_record.status = "failed"
                api_record.last_test_time = datetime.now()
                api_record.last_test_response = str(e)[:10000]
                with progress_lock:
                    test_progress['failed'] += 1
                    test_progress['results'].append({
                        'id': api_record.id,
                        'status': 'failed',
                        'response': str(e)[:2000]
                    })
            
            try:
                db.session.commit()
                logger.info(f"Batch test: Successfully saved status for API {api_record.id}")
            except Exception as commit_error:
                db.session.rollback()
                logger.error(f"Commit failed for API {api_record.id}: {commit_error}")

            with progress_lock:
                test_progress['completed'] += 1
        
        with progress_lock:
            test_progress['running'] = False
            test_progress['current_api'] = '完成'
    
    thread = threading.Thread(target=run_with_context)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": 0, 
        "resp": f"批量测试已启动，共 {len(apis)} 个接口",
        "total": len(apis)
    })


@main.route("/batch_test/progress/", methods=['GET'])
def batch_test_progress():
    """获取批量测试进度"""
    global test_progress
    with progress_lock:
        # 复制进度并清空 results 队列，防止前端重复处理
        current_data = test_progress.copy()
        test_progress['results'] = []
        return jsonify(current_data)


@main.route("/batch_test/stop/", methods=['POST'])
def batch_test_stop():
    """停止批量测试"""
    global test_progress
    with progress_lock:
        test_progress['running'] = False
    return jsonify({"status": 0, "resp": "已发送停止信号"})


@main.route("/api/<int:api_id>/status/", methods=['PUT'])
def update_api_status(api_id):
    """手动更新 API 状态"""
    req = request.json
    new_status = req.get('status')
    
    if new_status not in ['untested', 'success', 'failed']:
        return jsonify({"status": 1, "resp": "无效的状态值"})
    
    api_record = Apis.query.get(api_id)
    if not api_record:
        return jsonify({"status": 1, "resp": "API 不存在"})
    
    api_record.status = new_status
    db.session.commit()
    
    return jsonify({"status": 0, "resp": f"状态已更新为 {new_status}"})


@main.route("/api/delete_failed/", methods=['DELETE'])
def delete_failed_apis():
    """删除所有测试失败的接口"""
    try:
        count = Apis.query.filter(Apis.status == 'failed').delete()
        db.session.commit()
        return jsonify({"status": 0, "resp": f"成功删除 {count} 个无效接口"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 1, "resp": f"删除失败: {str(e)}"})


@main.route("/api/batch_delete/", methods=['POST'])
def batch_delete_apis():
    """批量删除指定接口"""
    try:
        req = request.json
        ids = req.get('ids')
        if not ids or not isinstance(ids, list):
            return jsonify({"status": 1, "resp": "参数错误"})
            
        count = Apis.query.filter(Apis.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"status": 0, "resp": f"成功删除 {count} 个接口"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 1, "resp": f"删除失败: {str(e)}"})


@main.route("/api/batch_status/", methods=['PUT'])
def batch_update_status():
    """批量更新接口状态"""
    try:
        req = request.json
        ids = req.get('ids')
        status = req.get('status')
        
        if not ids or not isinstance(ids, list) or status not in ['untested', 'success', 'failed']:
            return jsonify({"status": 1, "resp": "参数错误"})
            
        count = Apis.query.filter(Apis.id.in_(ids)).update({Apis.status: status}, synchronize_session=False)
        db.session.commit()
        return jsonify({"status": 0, "resp": f"成功更新 {count} 个接口状态"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": 1, "resp": f"更新失败: {str(e)}"})


@main.route("/api/stats/", methods=['GET'])
def api_stats():
    """获取接口统计信息"""
    total = Apis.query.count()
    success = Apis.query.filter(Apis.status == 'success').count()
    failed = Apis.query.filter(Apis.status == 'failed').count()
    untested = Apis.query.filter(Apis.status == 'untested').count()
    
    return jsonify({
        "total": total,
        "success": success,
        "failed": failed,
        "untested": untested
    })


@main.route("/api/export_json/", methods=['GET', 'POST'])
def export_json():
    """导出接口为 JSON，支持 ids 参数"""
    try:
        ids = None
        if request.method == 'POST':
            req_ids = request.form.get('ids')
            if req_ids:
                try:
                    ids = json.loads(req_ids)
                except:
                    pass
        
        query = Apis.query
        if ids and isinstance(ids, list) and len(ids) > 0:
            query = query.filter(Apis.id.in_(ids))
            
        apis = query.all()
        data = []
        for api in apis:
            api_data = {
                "desc": api.desc,
                "url": api.url,
                "method": api.method,
                "header": api.header,
                "data": api.data
            }
            
            # 尝试将字符串格式的 header/data 转回 JSON 对象，以便生成的 JSON 文件更易读
            # 如果存储的是 JSON 字符串，导出时转为对象
            try:
                if api_data['header'] and isinstance(api_data['header'], str):
                    # 简单的判断是否像 JSON
                    if api_data['header'].strip().startswith('{'):
                        api_data['header'] = json.loads(api_data['header'])
            except:
                pass
                
            try:
                if api_data['data'] and isinstance(api_data['data'], str):
                    if api_data['data'].strip().startswith('{'):
                        api_data['data'] = json.loads(api_data['data'])
            except:
                pass

            data.append(api_data)
            
        # 生成 JSON 响应并设置为下载
        json_str = json.dumps(data, ensure_ascii=False, indent=4)
        response = Response(json_str, mimetype='application/json; charset=utf-8')
        response.headers['Content-Disposition'] = 'attachment; filename=api_export.json'
        return response
    except Exception as e:
        logger.exception(e)
        return jsonify({"status": 1, "resp": f"导出失败: {str(e)}"})


@main.route("/api/import_json/", methods=['POST'])
def import_json():
    """从 JSON 导入接口"""
    try:
        if 'file' not in request.files:
            return jsonify({"status": 1, "resp": "没有上传文件"})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": 1, "resp": "未选择文件"})
            
        # 读取并解析 JSON
        try:
            content = json.load(file)
        except json.JSONDecodeError:
            return jsonify({"status": 1, "resp": "JSON 文件格式错误"})
            
        if not isinstance(content, list):
            return jsonify({"status": 1, "resp": "JSON 格式错误，根节点应为列表"})
            
        success_count = 0
        skip_count = 0
        
        for item in content:
            url = item.get('url')
            if not url:
                continue
                
            # 检查 URL 是否已存在
            exists = Apis.query.filter_by(url=url).first()
            if exists:
                skip_count += 1
                continue
                
            # 处理 header 和 data，如果是对象则转为 JSON 字符串存储
            header = item.get('header', '')
            if isinstance(header, (dict, list)):
                header = json.dumps(header, ensure_ascii=False)
            elif header is None:
                header = ""
            else:
                header = str(header)
                
            data = item.get('data', '')
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False)
            elif data is None:
                data = ""
            else:
                data = str(data)
            
            # 验证方法
            method = item.get('method', 'GET').upper()
            if method not in ['GET', 'POST']:
                method = 'GET'
                
            new_api = Apis(
                desc=item.get('desc', 'Default'),
                url=url,
                method=method,
                header=header,
                data=data,
                status='untested',
                add_time=datetime.now()
            )
            db.session.add(new_api)
            success_count += 1
            
        db.session.commit()
        return jsonify({
            "status": 0,
            "resp": f"导入完成：成功 {success_count} 个，跳过重复 {skip_count} 个",
            "success_count": success_count,
            "skip_count": skip_count
        })
        
    except Exception as e:
        db.session.rollback()
        logger.exception(e)
        return jsonify({"status": 1, "resp": f"导入失败: {str(e)}"})


# --- 采集管理相关路由 ---

@main.route("/scraper/", methods=['GET'])
def scraper_dashboard():
    """渲染采集管理主界面"""
    return render_template("scraper_dashboard.html")


def get_config_path():
    """获取配置文件路径，尝试多种策略"""
    # 策略1: 基于 current_app.root_path (最可靠，生产环境)
    root_path_1 = os.path.dirname(current_app.root_path)
    path_1 = os.path.join(root_path_1, "debug", "hz-web.json")
    
    # 策略2: 基于 os.getcwd() (开发环境/调试常见)
    path_2 = os.path.join(os.getcwd(), "debug", "hz-web.json")
    
    # 优先读取已存在的文件
    if os.path.exists(path_1):
        return path_1
    if os.path.exists(path_2):
        return path_2
        
    # 如果都不存在，默认返回 path_1 (优先在项目根目录创建)
    return path_1

@main.route("/api/scraper/sources/", methods=['GET'])
def get_scraper_sources():
    """获取采集源列表"""
    try:
        json_path = get_config_path()
        logger.info(f"Loading scraper sources from: {json_path}")
        
        if not os.path.exists(json_path):
            return jsonify([])
            
        with open(json_path, 'r', encoding='utf-8') as f:
            sources = json.load(f)
        return jsonify(sources)
    except Exception as e:
        logger.error(f"Error loading scraper sources: {e}")
        return jsonify([])


@main.route("/api/scraper/sources/save/", methods=['POST'])
def save_scraper_sources():
    """保存/更新采集源列表"""
    try:
        req = request.json
        sources = req.get('sources', [])
        
        json_path = get_config_path()
        logger.info(f"Saving scraper sources to: {json_path}")
        
        # 确保目录存在
        target_dir = os.path.dirname(json_path)
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
            except OSError as e:
                # 再次尝试在 cwd 下创建
                logger.warning(f"Failed to create directory {target_dir}: {e}. Trying fallback.")
                target_dir = os.path.join(os.getcwd(), "debug")
                json_path = os.path.join(target_dir, "hz-web.json")
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)
            
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sources, f, ensure_ascii=False, indent=4)
            
        return jsonify({"status": 0, "resp": "配置已成功保存"})
    except Exception as e:
        logger.error(f"Error saving scraper sources: {e}")
        return jsonify({"status": 1, "resp": f"保存失败: {str(e)}"})


@main.route("/api/scraper/run/", methods=['GET'])
def run_scraper():
    """执行采集任务 (SSE)"""
    from ..scraper_utils import get_scraper
    
    scraper_type = request.args.get('type', 'generic')
    url = request.args.get('url')
    key = request.args.get('key', '')

    if not url:
        return Response("data: {\"type\": \"error\", \"message\": \"Missing URL\"}\n\n", mimetype='text/event-stream')

    def generate():
        try:
            scraper = get_scraper(scraper_type, url, key)
            for event in scraper.scrape():
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@main.route("/api/scraper/import/", methods=['POST'])
def import_scraped_apis():
    """批量导入采集到的接口"""
    try:
        req = request.json
        apis_to_import = req.get('apis', [])
        
        if not apis_to_import:
            return jsonify({"status": 1, "resp": "没有可导入的接口"})

        success_count = 0
        skip_count = 0
        
        for item in apis_to_import:
            url = item.get('url')
            if not url:
                continue
                
            # 检查 URL 是否已存在
            exists = Apis.query.filter_by(url=url).first()
            if exists:
                skip_count += 1
                continue
                
            # 处理 header 和 data
            header = item.get('header', '')
            if isinstance(header, (dict, list)):
                header = json.dumps(header, ensure_ascii=False)
            
            data = item.get('data', '')
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False)
            
            new_api = Apis(
                desc=item.get('desc', '采集导入'),
                url=url,
                method=item.get('method', 'GET').upper(),
                header=header,
                data=data,
                status='untested',
                last_test_response=item.get('response', ''), # 导入捕获到的响应内容
                add_time=datetime.now()
            )
            db.session.add(new_api)
            success_count += 1
            
        db.session.commit()
        return jsonify({
            "status": 0,
            "resp": f"成功导入 {success_count} 个接口，跳过 {skip_count} 个重复项",
            "success_count": success_count
        })
        
    except Exception as e:
        db.session.rollback()
        logger.exception(e)
        return jsonify({"status": 1, "resp": f"导入失败: {str(e)}"})


@main.route("/api/cleanup/", methods=['POST'])
def cleanup_apis():
    """整理 ID 并且去重"""
    try:
        # 1. 去重 (基于 URL)
        # 找出重复的 URL，只保留 ID 最小的那个
        # 注意：SQLite 不支持直接 DELETE ... USING ... JOIN 语法，需要变通
        
        # 查找重复的 URL 及其对应的 ID
        # 这是一个比较通用的 SQL 写法，但在 ORM 中我们可能需要手动处理一下以兼容不同 DB
        
        all_apis = Apis.query.order_by(Apis.id).all()
        seen_urls = {}
        ids_to_delete = []
        
        for api in all_apis:
            if api.url in seen_urls:
                ids_to_delete.append(api.id)
            else:
                seen_urls[api.url] = api.id
                
        # 执行删除
        if ids_to_delete:
            Apis.query.filter(Apis.id.in_(ids_to_delete)).delete(synchronize_session=False)
            db.session.commit()
            
        # 2. 整理 ID (重建表或重置自增)
        # 在 SQLite/MySQL 中，整理 ID 比较复杂，通常涉及到重置 AUTO_INCREMENT。
        # 简单的做法是：如果不强制要求 ID 连续，只做去重即可。
        # 如果非要 ID 连续，可能需要大量数据迁移，这里我们做一个简单的“重新排序”：
        # 创建新表 -> 插入数据 -> 删除旧表 -> 重命名新表 (这是 SQLite 标准做法，但 SQLAlchemy 操作较重)
        #
        # 替代方案：不做物理 ID 重排（风险大），只做去重。
        # 用户的需求是 "整理 id 并且去重"，"整理 id" 可能是指填补空缺或重置。
        # 考虑到风险，我们先只做去重，并返回去重数量。
        # 如果用户一定要 ID 连续，可以建议导出再导入。
        # 但既然提到了 "整理 ID"，我们可以尝试做一个软性的 ID 重置（如果数据量不大）：
        # 获取所有剩余数据 -> 清空表 -> 重置自增 -> 重新插入
        
        duplicate_count = len(ids_to_delete)
        reordered = False
        
        # 如果去重后数据量不大（例如 < 10000），可以尝试重排 ID
        remaining_count = Apis.query.count()
        if remaining_count < 10000:
            apis = Apis.query.order_by(Apis.id).all()
            
            # 保存所有数据到内存
            api_data_list = []
            for api in apis:
                api_data_list.append({
                    'desc': api.desc,
                    'url': api.url,
                    'method': api.method,
                    'header': api.header,
                    'data': api.data,
                    'status': api.status,
                    'last_test_time': api.last_test_time,
                    'last_test_response': api.last_test_response,
                    'add_time': api.add_time
                })
            
            # 清空表
            Apis.query.delete()
            db.session.commit()
            
            # 重置自增 ID (SQLite)
            # db.session.execute("DELETE FROM sqlite_sequence WHERE name='apis'") # 如果表名是 apis
            # 这里的表名取决于 SQLAlchemy 的模型名，通常是类名的小写或 __tablename__
            try:
                # 尝试重置 SQLite 的自增计数器
                db.session.execute("DELETE FROM sqlite_sequence WHERE name='apis'")
            except:
                pass # 可能不是 SQLite 或者表名不对
                
            # 重新插入
            for data in api_data_list:
                db.session.add(Apis(**data))
            
            db.session.commit()
            reordered = True

        return jsonify({
            "status": 0,
            "resp": f"清理完成：去重 {duplicate_count} 个接口" + ("，并已重新排列 ID" if reordered else " (仅去重，ID未重排)"),
            "duplicate_count": duplicate_count,
            "reordered": reordered
        })
        
    except Exception as e:
        db.session.rollback()
        logger.exception(e)
        return jsonify({"status": 1, "resp": f"清理失败: {str(e)}"})


# --- Playwright 抓包相关路由 ---

@main.route("/capture/", methods=['GET'])
def capture_dashboard():
    """渲染抓包管理界面"""
    return render_template("capture_dashboard.html")

@main.route("/api/capture/start/", methods=['POST'])
def capture_start():
    """启动 Playwright 抓包会话"""
    from ..playwright_capture import capture_manager
    
    req = request.json
    phone = req.get('phone')
    initial_urls = req.get('initial_urls')
    user_data_dir = req.get('user_data_dir') # 可选：自定义用户数据目录
    use_system_profile = req.get('use_system_profile', False)
    
    if not phone:
        return jsonify({"status": 1, "resp": "请提供测试手机号"})
        
    try:
        # 如果没有提供 user_data_dir，manager 会使用默认的 browser_data 目录
        capture_manager.start_capture(phone, initial_urls, user_data_dir, use_system_profile)
        return jsonify({"status": 0, "resp": "抓包会话已启动 (持久化模式)"})
    except RuntimeError as e:
        return jsonify({"status": 1, "resp": str(e)})
    except Exception as e:
        logger.exception(e)
        return jsonify({"status": 1, "resp": f"启动失败: {str(e)}"})

@main.route("/api/capture/stop/", methods=['POST'])
def capture_stop():
    """停止 Playwright 抓包会话"""
    from ..playwright_capture import capture_manager
    try:
        capture_manager.stop_capture()
        return jsonify({"status": 0, "resp": "已发送停止信号"})
    except Exception as e:
        return jsonify({"status": 1, "resp": f"停止失败: {str(e)}"})

@main.route("/api/capture/events/", methods=['GET'])
def capture_events():
    """获取抓包事件流 (SSE)"""
    from ..playwright_capture import capture_manager
    
    def generate():
        while True:
            events = capture_manager.get_events()
            if events:
                for event in events:
                    yield f"data: {json.dumps(event)}\n\n"
            else:
                # 保持连接活跃
                yield ": keep-alive\n\n"
            
            import time
            time.sleep(0.5)
            
            # 如果不再运行且队列为空，可以考虑关闭连接，或者保持等待
            # 这里简单处理：只要连接不断开就一直轮询
            
    return Response(generate(), mimetype='text/event-stream')
