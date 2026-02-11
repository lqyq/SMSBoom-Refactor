# encoding=utf8
# 储存数据库模型
from utils import default_header_user_agent
from . import db
from datetime import datetime
# from . import ModelView
from flask_admin.contrib.sqla import ModelView
import json
import html
from typing import Union, Optional
from pydantic import BaseModel
from flask import flash, redirect, url_for, request
from flask_admin.actions import action
from flask_admin import expose
from markupsafe import Markup

class ApisModelVies(ModelView):
    create_template = 'api_edit.html'
    edit_template = 'api_edit.html'
    list_template = 'api_list.html'
    # 新增：定义状态和方法的选取项
    column_choices = {
        'status': [
            ('untested', '⚪ 未测'),
            ('success', '✅ 有效'),
            ('failed', '❌ 无效'),
        ],
        'method': [
            ('GET', 'GET'),
            ('POST', 'POST'),
        ]
    }

    @expose('/')
    def index_view(self):
        # 允许通过 URL 参数动态设置界面风格
        ui_style = request.args.get('style', 'default')
        original_template = self.list_template
        if ui_style == 'beautiful':
            self.list_template = 'api_list_beautiful.html'
        
        # 允许通过 URL 参数动态设置分页大小
        page_size = request.args.get('page_size', type=int)
        if page_size and page_size > 0:
            self.page_size = page_size
        else:
            self.page_size = 20
            
        try:
            return super(ApisModelVies, self).index_view()
        finally:
            self.list_template = original_template

    # 在当前页面编辑
    # create_modal = True
    # edit_modal = True
    # 启用搜索
    column_searchable_list = ['desc']
    # 可以导出 csv
    can_export = True
    
    # 定义列显示
    column_list = ['id', 'desc', 'method', 'url', 'header', 'data', 'status', 'last_test_response', 'last_test_time', 'add_time']
    
    column_labels = {
        'id': 'ID',
        'desc': '描述',
        'url': '接口地址',
        'method': '方法',
        'header': '请求头',
        'data': '请求数据',
        'status': '状态',
        'last_test_response': '响应内容',
        'last_test_time': '测试时间',
        'add_time': '添加时间'
    }
    
    # 状态列格式化
    column_formatters = {
        'status': lambda v, c, m, p: Markup(f'<div class="status-clickable" data-api-id="{m.id}" style="cursor:pointer" title="点击手动修改状态">' + ({
            'untested': '<span class="label label-default">⚪ 未测</span>',
            'success': '<span class="label label-success">✅ 有效</span>',
            'failed': '<span class="label label-danger">❌ 无效</span>'
        }.get(m.status, '<span class="label label-default">⚪</span>')) + '</div>'),
        'url': lambda v, c, m, p: Markup(f'<span title="{html.escape(str(m.url))}" class="text-content">{html.escape(str(m.url))}</span>'),
        'header': lambda v, c, m, p: Markup(f'<span title="{html.escape(str(m.header or ""))}" class="text-content">{html.escape(str(m.header or ""))}</span>'),
        'data': lambda v, c, m, p: Markup(f'<span title="{html.escape(str(m.data or ""))}" class="text-content">{html.escape(str(m.data or ""))}</span>'),
        'last_test_response': lambda v, c, m, p: Markup(f'<span title="{html.escape(str(m.last_test_response or ""))}" class="text-content">{html.escape(str(m.last_test_response or ""))}</span>'),
        'last_test_time': lambda v, c, m, p: Markup(f'<span class="test-time-cell">{m.last_test_time.strftime("%H:%M:%S") if m.last_test_time else "-"}</span>')
    }
    
    # 允许排序的列
    column_sortable_list = ['id', 'desc', 'url', 'method', 'header', 'data', 'status', 'last_test_response', 'last_test_time', 'add_time']
    
    # 允许查看详情
    can_view_details = True
    
    # 详情页格式化 - 避免详情页内容被截断，并使用 pre 标签保持格式
    column_formatters_detail = {
        'url': lambda v, c, m, p: m.url,
        'header': lambda v, c, m, p: Markup(f'<pre style="white-space: pre-wrap; word-break: break-all;">{html.escape(str(m.header or ""))}</pre>') if m.header else "",
        'data': lambda v, c, m, p: Markup(f'<pre style="white-space: pre-wrap; word-break: break-all;">{html.escape(str(m.data or ""))}</pre>') if m.data else "",
        'last_test_response': lambda v, c, m, p: Markup(f'<pre style="white-space: pre-wrap; word-break: break-all;">{html.escape(str(m.last_test_response or ""))}</pre>') if m.last_test_response else ""
    }

    # 按状态筛选
    column_filters = ['status', 'method', 'desc']

    # 添加单行操作按钮
    def _list_row_actions(self):
        actions = super(ApisModelVies, self)._list_row_actions()        # 获取默认的行操作
        actions.append({
            'url': lambda m, p: url_for('.custom_action_view', id=getattr(m, self._primary_key)),
            'title': '自定义操作',
            'icon': 'fa fa-gear'
        })        # 添加自定义操作
        return actions
    
    # 批量删除无效接口
    @action('delete_failed', '删除无效接口', '确定要删除所有测试失败的接口吗？')
    def action_delete_failed(self, ids):
        try:
            query = Apis.query.filter(Apis.id.in_(ids), Apis.status == 'failed')
            count = query.count()
            query.delete(synchronize_session='fetch')
            db.session.commit()
            flash(f'成功删除 {count} 个无效接口', 'success')
        except Exception as ex:
            flash(f'删除失败: {str(ex)}', 'error')
    
    # 处理自定义操作
    # @expose('/custom_action/<int:id>', methods=['GET'])
    # def custom_action_view(self, id):
        # 获取记录
        # model = self.model
        # record = self.session.query(model).get(id)
        # if record is None:
        #     flash('记录不存在', 'error')
        #     return redirect(url_for('.index_view'))
        # 执行自定义操作
        # try:
        #     model.some_field = 'new_value'
        #     self.session.commit()
        #     flash('操作成功执行')
        # except Exception as ex:
        #     flash('操作失败: %s' % str(ex), 'error')
        # return redirect(url_for('.index_view'))

class Apis(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # 主键
    desc = db.Column(db.String(20), default="Default")  # 描述
    url = db.Column(db.String(9999), unique=True, nullable=False)  # 链接
    method = db.Column(db.Enum("GET", "POST"), nullable=False)  # 请求方法
    header = db.Column(db.String(9999))  # 请求头
    data = db.Column(db.String(9999))  # 请求数据
    add_time = db.Column(db.DateTime(), default=datetime.now)  # 添加时间
    # 新增：测试状态字段
    status = db.Column(db.String(20), default="untested")  # untested, success, failed
    last_test_time = db.Column(db.DateTime())  # 最后测试时间
    last_test_response = db.Column(db.Text())  # 最后测试响应


class API(BaseModel):
    desc: str = "Default"
    url: str
    method: str = "GET"
    header: Optional[Union[str, dict]] = default_header_user_agent()
    data: Optional[Union[str, dict]]

    def replace_data(self, content: Union[str, dict], phone) -> str:
        # 统一转换成 str 再替换.
        content = str(content).replace("[phone]", phone).replace(
            "[timestamp]", self.timestamp_new()).replace("'", '"')
        # 尝试 json 化
        try:
            # json.loads(content)
            # print("json成功",content)
            return json.loads(content)
        except:
            # print("json失败",content)
            return content

    def timestamp_new(self) -> str:
        """返回整数字符串时间戳"""
        return str(int(datetime.now().timestamp()))

    def handle_API(self, phone=None):
        """
        :param API: one API basemodel
        :return: API basemodel
        """
        # 仅仅当传入 phone 参数时添加 Referer
        # fix: 这段代码很有问题.......
        if phone:
            # 进入的 header 是个字符串
            if self.header == "":
                self.header = {}
                self.header['Referer'] = self.url  # 增加 Referer

        self.header = self.replace_data(self.header, phone)
        if not self.header.get('Referer'):
            self.header['Referer'] = self.url  # 增加 Referer

        self.data = self.replace_data(self.data, phone)
        self.url = self.replace_data(self.url, phone)
        # print(self)
        return self
