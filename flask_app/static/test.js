

function getValue() {
    let desc = $("#desc").val();
    let url = $("#url").val();
    let method = $("#method").val();
    let header = $("#header").val();
    let phone = $("#phone").val();
    let data_ = $("#data").val();

    // 如果是通过 Flask-Admin 的编辑界面，ID 可能不同
    if (!desc) desc = $("input[name='desc']").val();
    if (!url) url = $("input[name='url']").val();
    if (!method) method = $("select[name='method']").val();
    if (!header) header = $("textarea[name='header']").val();
    if (!data_) data_ = $("textarea[name='data']").val();

    let data = {
        "desc": desc,
        "url": url,
        "method": method,
        "header": header,
        "phone": phone,
        "data": data_
    };

    return data;
};

$(document).ready(function () {

    // 加载上次使用的手机号
    let lastPhone = localStorage.getItem("last_test_phone");
    if (lastPhone) {
        $("#phone").val(lastPhone);
    }

    $("#test").click(function () {
        let testData = getValue();
        
        // 记住手机号
        if (testData.phone) {
            localStorage.setItem("last_test_phone", testData.phone);
        }

        const $suc = $("#suc");
        const $error = $("#error");

        $suc.hide().attr("class", "alert alert-info").text("正在请求...").show();
        $error.hide();

        $.ajax({
            type: "POST",
            url: "/testapi/",
            contentType: "application/json",
            data: JSON.stringify(testData),
            dataType: "json",
            success: function (response) {
                if (response.status == 0) {
                    $suc.attr("class", "alert alert-success").show().html("<strong>请求成功!</strong><br><pre style='margin-top:10px; max-height:400px; overflow:auto;'>" + response.resp + "</pre>");
                } else {
                    $suc.attr("class", "alert alert-warning").show().html("<strong>请求失败!</strong><br><pre style='margin-top:10px; max-height:400px; overflow:auto;'>" + response.resp + "</pre>");
                }
            },
            error: function (XMLHttpRequest, textStatus, errorThrown) {
                $error.show().text("发送请求错误请检查后端接口:" + textStatus);
                $suc.hide();
            },
        });

    });

    // console.log(desc, url, method, header);


});
