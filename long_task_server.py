import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi import Request, Response
# from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager

# 422 error handle
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from fastapi import Request, Depends, Query, Path, Form, File, Body
from fastapi.security import HTTPBearer
from nice_serving_backend.utils.schemas import (
    SaveSegmentRefitHistory, ApplyNiceAutoML,
    GetFineClassingReport, PredictSegment
)

import functools
import getopt
import sys
import os
import ssl
import asyncio
import signal
import traceback
import json
import urllib.error
import urllib.request
from urllib import parse
from uuid import uuid4
import logging
import time

from nice_serving_backend.constants import constants
from nice_serving_backend.executors.serving import refit_executor
from nice_serving_backend.executors.serving import automl_executor
from nice_serving_backend.executors.serving import segment_executor
from nice_serving_backend.utils import common_utils, web_utils, db_utils, data_utils


####################################################################################################
#============================================== setup ==============================================#
####################################################################################################
# config 설정
config_file_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.ini"
)
config = common_utils.load_config(config_file_path)

# access logger 설정
log_file_path = os.path.join(config["ROOT_DIR"])
common_utils.setup_logging(log_file_path)

access_logger = logging.getLogger("NICE_Access_Logger")


####################################################################################################
#=========================================== init server ===========================================#
####################################################################################################
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.config = config
        yield
    except Exception as e:
        raise Exception(str(e))


security = HTTPBearer(auto_error=False)
# app def
app = FastAPI(lifespan=lifespan, docs_url=None, dependencies=[Depends(security)])


####################################################################################################
#======================================= swagger ui setting =======================================#
####################################################################################################
# static 폴더
app.mount("/static", StaticFiles(directory=f"{os.path.dirname(os.path.abspath(__file__))}/static"), name="static")

#/docs
@app.get("/docs", include_in_schema=False)
def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="test",
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
        # swagger_ui_preset_url="/static/swagger-ui-standalone-preset.js",
    )


# 422 unprocessable entity 해결을 위해 추가
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"invalid data: {exc.body}")
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": exc.errors(), "body": exc.body})
    )


####################################################################################################
#======================================== internal function ========================================#
####################################################################################################
def _get_next_h2o_port(app):
    # figure out the port with the most free memory
    h2o_host = app["H2O_SERVER_HOST"]
    h2o_port, h2o_free_mem = -1, -1
    for h2o_timeout in [0.1, 0.5, 1, 2, 5]:
        for next_h2o_port in app["H2O_SERVER_PORTS"]:
            if _h2o_health_check(h2o_host, next_h2o_port, h2o_timeout):
                next_h2o_free_mem = _h2o_free_mem(h2o_host, next_h2o_port)
                if h2o_free_mem < next_h2o_free_mem:
                    h2o_free_mem = next_h2o_free_mem
                    h2o_port = next_h2o_port
        if h2o_port > -1:
            break
    if h2o_port > -1:
        return h2o_port
    else:
        raise Exception("No h2o port available. Please try again later.")


def _h2o_free_mem(h2o_host, h2o_port):
    concat_h2o_cloud_url = (
        "http://" + web_utils.concat_host_and_port(h2o_host, h2o_port) + "/3/Cloud"
    )
    try:
        h2o_cloud_info = json.loads(web_utils.http_get(concat_h2o_cloud_url))
        free_mem = sum(node["free_mem"] for node in h2o_cloud_info["nodes"])
        return free_mem
    except Exception as e:
        return -1


def _h2o_health_check(h2o_host, h2o_port, h2o_timeout):
    # when h2o.init, it doesn't require scheme
    concat_h2o_url = "http://" + web_utils.concat_host_and_port(h2o_host, h2o_port)
    try:
        return (
            urllib.request.urlopen(concat_h2o_url, timeout=h2o_timeout).getcode() == 200
        )
    except urllib.error.URLError:
        return False
    except:
        return False


# [2019-12-05] pjh - get current process lock(set lock if not exists)
def _get_current_process_lock(app):
    app_pid = os.getpid()
    if app_pid not in app["PROCESS_LOCK_DICT"]:
        app["PROCESS_LOCK_DICT"][app_pid] = asyncio.Lock()

    return app["PROCESS_LOCK_DICT"][app_pid]


async def app_cleanup_handler(app):
    app_pid = os.getpid()
    if app_pid in app["PROCESS_LOCK_DICT"]:
        async with app["PROCESS_LOCK_DICT"][app_pid]:
            pass


#/serving/task/sendreport/excel-report
@app.post("/serving/task/sendreport/excel-report")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_sendreport_excel_report(request: Request, body: GetSendreportExcelReport):
    """
    기존 get -> post 변경
    """

    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # user_id = "tester"  # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        # company_code = "Sv"  # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        # company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
        # company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        # auth_key = request.query_params["auth-key"]
        product_id = json_obj["ProductId"]
        report_type = json_obj["ReportType"]
        report_format = json_obj["ReportFormat"]
        report_score_type = json_obj["ReportScoreType"]

        flow_ids = json_obj["Segments"]
        base_yms = json_obj["BaseTime"]
        compare_yms = json_obj["CompTime"]

        base_desc = json_obj["BaseTimeDesc"]
        compare_desc = json_obj["CompTimeDesc"]

        exec_func = functools.partial(
            serving_task_executor.get_sendreport_to_excel_report,
            service_db_info=service_db_info,
            # auth_key=auth_key,
            product_id=product_id,
            report_type=report_type,
            report_format=report_format,
            report_score_type=report_score_type,
            flow_ids=flow_ids,
            base_yms=base_yms,
            compare_yms=compare_yms,
            base_desc=base_desc,
            compare_desc=compare_desc,
        )
        model_bytes = await asyncio.to_thread(exec_func)

        return await web_utils.stream_response(model_bytes, request)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/task/sendreport/refit-info
@app.post("/serving/task/sendreport/refit-info")
@web_utils.web_err_handler
@web_utils.auth_handler
async def get_serving_refit_report_info(request: Request, body: GetServingRefitReportInfo,
                                         product_id: int | None = Query(default=None, alias='id'),
                                         file_name: str | None = Query(default=None, alias='file-name')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        # auth_key = request.query_params["auth-key"]
        # product_id = json_obj["ProductId"]
        # TODO [2026-06-26 dyk] 파라미터명 카멜케이스로 변경 필요
        flow_ids = json_obj["Segments"]
        compare_yms = json_obj["compare-yms"]
        score_unit = json_obj["score-unit"]
        task_yn = json_obj["task-yn"]

        if (
            "product-id" in request.query_params
            and "file-name" in request.query_params
        ):
            ##### report history
            """
            get_company_info_func = functools.partial(
                db_utils.get_company_and_user_info,
                service_db_info=service_db_info,
                auth_key=auth_key,
            )
            company_and_user_info = await asyncio.to_thread(get_company_info_func)
            company_code = company_and_user_info.company_code

            get_report_file_url_func = functools.partial(
                data_utils.get_file_url,
                file_server_host=app_config["FILE_SERVER_HOST"],
                file_server_port=app_config["FILE_SERVER_PORT"],
                company_code=company_code,
                file_name=request.query_params["file-name"],
                file_type_flag=constants.FileTypeFlag.SERVING_REPORT,
                ml_process_seq=request.query_params["product-id"],
            )
            report_file_url = await asyncio.to_thread(get_report_file_url_func)

            exec_func = functools.partial(
                web_utils.get_bytes_from_url, url=report_file_url
            )

            report_file_bytes = await asyncio.to_thread(exec_func)
            refit_info_json = json.loads(report_file_bytes)
            """
            refit_info_json = {}
        else:
            #
            exec_func = functools.partial(
                serving_task_executor.get_serving_refit_report_info,
                service_db_info=service_db_info,
                # auth_key=auth_key,
                company_code=json_obj["CompanyCode"],
                company_db_info=company_db_info,
                flow_ids=flow_ids,
                compare_yms=compare_yms,
                score_unit=int(score_unit),
                task_yn=int(task_yn),
            )

            refit_info_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(refit_info_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


# TODO - Report Sample
#/serving/task/sendreport/gettest
@app.post("/serving/task/sendreport/gettest")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_sendreport_gettest(request: Request, body: GetSendreportGettest):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        # test_filename = request.query_params["filename"]
        # TODO [2026-06-26 dyk] 파라미터명 카멜케이스로 변경 필요
        filetype = json_obj["filetype"]  # Monitoring, Refit

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_task_executor.get_sendreport_gettest,
            service_db_info=service_db_info,
            filetype=filetype,
        )
        model_bytes = await asyncio.to_thread(exec_func)

        return await web_utils.stream_response(model_bytes, request)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


####################################################################################################
#=========================================== run server ============================================#
####################################################################################################
if __name__ == "__main__":
    try:
        opts, args = getopt.getopt(sys.argv[1:], "p:", ["port=", "use-ssl"])
    except getopt.GetoptError as err:
        print(str(err))
        sys.exit(1)

    service_port_specified = False
    # default port
    service_port = 12345
    use_ssl = False

    for opt, arg in opts:
        if opt == "-p" or opt == "--port":
            service_port = int(arg)
            service_port_specified = True
        elif opt == "--use-ssl":
            use_ssl = True
        else:
            print("Unknown option.")
            sys.exit(1)

    # port option is not required.
    if not service_port_specified:
        print("The port is set to a default port {0}.".format(service_port))

    # ssl configuration
    # it uses key files in root directory
    ssl_context = None
    if use_ssl:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_cert_path = config_file_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "ssl", "server.crt"
        )
        ssl_key_path = config_file_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "ssl", "server.key"
        )
        ssl_context.load_cert_chain(ssl_cert_path, ssl_key_path)

    uvicorn.run("nice_serving_backend.task_server.short_task_server:app",
                host="0.0.0.0", port=service_port, access_log=False)
    app_pid = os.getpid()
    if app_pid in app["PROCESS_LOCK_DICT"]:
        async with app["PROCESS_LOCK_DICT"][app_pid]:
            pass

    print("Cleaning up {}...".format(app_pid))
    os.kill(app_pid, signal.SIGINT)


####################################################################################################
#============================================= handlers =============================================#
####################################################################################################
@app.middleware("http")
async def set_access_logger(request: Request, call_next):
    request_id = str(uuid4())
    start_time = time.perf_counter()

    request.state.request_id = request_id

    # TODO keycloak 설정 후 keycloak 사용자 이름 받도록 수정
    user_id = "tester"
    client_ip = request.client.host if request.client else "unknown"
    try:
        response = await call_next(request)
    except Exception:
        duration = (time.perf_counter() - start_time) * 1000

        access_logger.exception(
            "Unexpected middleware failure | request_id=%s user_id=%s method=%s path=%s client_ip=%s duration_ms=%.2f",
            request_id,
            user_id,
            request.method,
            request.url.path,
            client_ip,
            duration
        )
        raise

    duration = (time.perf_counter() - start_time) * 1000
    route = request.scope.get("route")
    endpoint = (
        route.endpoint.__name__
        if route and hasattr(route, "endpoint")
        else "-"
    )

    access_logger.info(
        "request_id=%s user_id=%s method=%s endpoint=%s path=%s status=%d duration_ms=%.2f client_ip=%s",
        request_id,
        user_id,
        request.method,
        endpoint,
        request.url.path,
        response.status_code,
        duration,
        client_ip
    )

    return response


####################################################################################################
#============================================ api start ============================================#
####################################################################################################
# polling 대체 API 작성(파일 대신 DB 에서 정보 읽어온다.)
#/serving/long-task/status
@app.get('/serving/long-task/status')
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_check_task_status(request: Request, product_id: int = Query(alias='product-id'),
                                     task_type: str = Query(alias='task-type')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        product_id = request.query_params['product-id']
        # user_id = request.query_params['user-id']
        task_type = request.query_params['task-type']

        # TODO user_id 는 keycloak 통해서 세팅
        user_id = "tester"
        company_code = "Sv"

        exec_func = functools.partial(
            refit_executor.get_long_task_status,
            service_db_info=service_db_info,
            company_code=company_code,
            product_id=product_id,
            user_id=user_id,
            task_type=task_type,
        )

        long_task_status = await asyncio.to_thread(exec_func)

        return web_utils.json_response(long_task_status)

    except Exception as e:
        app_config['ERROR_LOGGER'].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment/refit
@app.post("/serving/segment/refit")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_refit_model(request: Request, body: str = Body(media_type="text/plain")):
    app_state = request.app.state
    app_config = app_state.config

    json_obj = await request.json()

    # TODO faf 삭제
    file_name_key = str(uuid4())
    json_obj["FireAndForgetResultFileName"] = 'result_' + file_name_key
    json_obj["FireAndForgetErrorFileName"] = 'error_' + file_name_key
    json_obj["FireAndForgetDoneFileName"] = 'done_' + file_name_key

    (
        result_file_path_faf,
        error_file_path_faf,
        done_file_path_faf,
    ) = common_utils.prepare_fire_and_forget_from_json(app_config["ROOT_DIR"], json_obj)

    # TODO keycloak 에서 user_id, company_code 설정
    company_code = "Sv"
    user_id = "tester"

    try:
        async with _get_current_process_lock(app_config):
            service_db_info = db_utils.get_service_db_info_from_app(app_config)

            exec_func = functools.partial(
                automl_executor.run_rebuild,
                service_db_info=service_db_info,
                root_dir=app_config["ROOT_DIR"],            # [2025-10-30] hash1 - 추가
                file_server_host=app_config["FILE_SERVER_HOST"],
                file_server_port=app_config["FILE_SERVER_PORT"],
                h2o_file_server_host=app_config["H2O_FILE_SERVER_HOST"],
                h2o_file_server_port=app_config["H2O_FILE_SERVER_PORT"],
                company_code=company_code,
                user_id=user_id,
                numpy_use_32bit_float_precision=app_config["NUMPY_USE_32BIT_FLOAT_PRECISION"],
                h2o_host=app_config["SERVING_H2O_SERVER_HOST"],
                h2o_port=app_config["SERVING_H2O_SERVER_PORT"],
                h2o_older_version_port=app_config["H2O_OLDER_VERSION_PORT"],
                json_obj=json_obj,
                result_file_path_faf=result_file_path_faf,
                done_file_path_faf=done_file_path_faf
            )

            await asyncio.to_thread(exec_func)

            return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        with open(error_file_path_faf, "w") as efd, open(
            done_file_path_faf, "w"
        ) as dfd:
            efd.write(str(e))
            dfd.write(constants.FAF_ERROR_STRING)
        raise


#/serving/segment/refit-history
@app.post("/serving/segment/refit-history")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_save_segment_refit_history(request: Request, body: SaveSegmentRefitHistory):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        exec_func = functools.partial(
            refit_executor.save_segment_refit_history,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            h2o_host=app_config["SERVING_H2O_SERVER_HOST"],
            h2o_port=app_config["SERVING_H2O_SERVER_PORT"],
            h2o_file_server_host=app_config["H2O_FILE_SERVER_HOST"],
            h2o_file_server_port=app_config["H2O_FILE_SERVER_PORT"],
            h2o_older_version_port=app_config["H2O_OLDER_VERSION_PORT"],
            root_dir=app_config["ROOT_DIR"],
            json_obj=json_obj,
        )

        new_history_id = await asyncio.to_thread(exec_func)

        return Response(content=str(new_history_id))

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/file/intermediate-pred-dir
@app.get("/serving/file/intermediate-pred-dir")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_file_in_intermediate_pred_dir(request: Request):
    app_state = request.app.state
    app_config = app_state.config
    try:
        auth_key = request.query_params["auth-key"]
        file_name = request.query_params["file-name"]
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        get_company_info_func = functools.partial(
            db_utils.get_company_and_user_info,
            service_db_info=service_db_info,
            auth_key=auth_key,
        )

        company_and_user_info = await asyncio.to_thread(get_company_info_func)
        company_code = company_and_user_info.company_code

        exec_func = functools.partial(
            data_utils.get_file_url,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            file_name=file_name,
            file_type_flag=constants.FileTypeFlag.INTERMEDIATE_FILE,
        )

        file_url = await asyncio.to_thread(exec_func)

        return await web_utils.chunked_remote_file_response(file_url, request)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment/rebuild
@app.post("/serving/segment/rebuild")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_segment_rebuild(request: Request):
    app_state = request.app.state
    app_config = app_state.config
    json_obj = await request.json()
    # TODO faf 삭제
    file_name_key = str(uuid4())
    json_obj["FireAndForgetResultFileName"] = 'result_' + file_name_key
    json_obj["FireAndForgetErrorFileName"] = 'error_' + file_name_key
    json_obj["FireAndForgetDoneFileName"] = 'done_' + file_name_key

    (
        result_file_path_faf,
        error_file_path_faf,
        done_file_path_faf,
    ) = common_utils.prepare_fire_and_forget_from_json(app_config["ROOT_DIR"], json_obj)

    # TODO keycloak 에서 user_id, company_code 설정
    company_code = "Sv"
    user_id = "tester"

    try:
        async with _get_current_process_lock(app_config):
            service_db_info = db_utils.get_service_db_info_from_app(app_config)

            company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
            company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

            exec_func = functools.partial(
                automl_executor.run_rebuild,
                service_db_info=service_db_info,
                company_code=company_code,
                user_id=user_id,
                file_server_host=app_config["FILE_SERVER_HOST"],
                file_server_port=app_config["FILE_SERVER_PORT"],
                h2o_file_server_host=app_config["H2O_FILE_SERVER_HOST"],
                h2o_file_server_port=app_config["H2O_FILE_SERVER_PORT"],
                numpy_use_32bit_float_precision=app_config["NUMPY_USE_32BIT_FLOAT_PRECISION"],
                result_file_path_faf=result_file_path_faf,
                done_file_path_faf=done_file_path_faf,
                h2o_host=app_config["SERVING_H2O_SERVER_HOST"],
                h2o_port=_get_next_h2o_port(app_config),
                h2o_older_version_port=app_config["H2O_OLDER_VERSION_PORT"],
                root_dir=app_config["ROOT_DIR"],
                json_obj=json_obj,
            )

            await asyncio.to_thread(exec_func)

            return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        with open(error_file_path_faf, "w") as efd, open(
            done_file_path_faf, "w"
        ) as dfd:
            efd.write(str(e))
            dfd.write(constants.FAF_ERROR_STRING)
        raise


#/serving/segment/nice-auto-ml/fit
@app.post("/serving/segment/nice-auto-ml/fit")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_fit_nice_auto_ml(request: Request, body: str = Body(media_type="text/plain")):
    app_state = request.app.state
    app_config = app_state.config
    json_obj = await request.json()
    # TODO faf 삭제
    file_name_key = str(uuid4())
    json_obj["FireAndForgetResultFileName"] = 'result_' + file_name_key
    json_obj["FireAndForgetErrorFileName"] = 'error_' + file_name_key
    json_obj["FireAndForgetDoneFileName"] = 'done_' + file_name_key

    (
        result_file_path_faf,
        error_file_path_faf,
        done_file_path_faf,
    ) = common_utils.prepare_fire_and_forget_from_json(app_config["ROOT_DIR"], json_obj)

    # TODO keycloak 에서 user_id, company_code 설정
    company_code = "Sv"
    user_id = "tester"

    try:
        async with _get_current_process_lock(app_config):
            service_db_info = db_utils.get_service_db_info_from_app(app_config)

            company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
            company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

            exec_func = functools.partial(
                automl_executor.run_rebuild,
                service_db_info=service_db_info,
                company_code=company_code,
                user_id=user_id,
                file_server_host=app_config["FILE_SERVER_HOST"],
                file_server_port=app_config["FILE_SERVER_PORT"],
                h2o_file_server_host=app_config["H2O_FILE_SERVER_HOST"],
                h2o_file_server_port=app_config["H2O_FILE_SERVER_PORT"],
                numpy_use_32bit_float_precision=app_config["NUMPY_USE_32BIT_FLOAT_PRECISION"],
                result_file_path_faf=result_file_path_faf,
                done_file_path_faf=done_file_path_faf,
                h2o_host=app_config["SERVING_H2O_SERVER_HOST"],
                h2o_port=_get_next_h2o_port(app_config),
                root_dir=app_config["ROOT_DIR"],
                json_obj=json_obj,
            )

            await asyncio.to_thread(exec_func)

            return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        with open(error_file_path_faf, "w") as efd, open(
            done_file_path_faf, "w"
        ) as dfd:
            efd.write(str(e))
            dfd.write(constants.FAF_ERROR_STRING)
        raise
# [2024-09-05] ldk - add auto ml
# @app.post("/ml/model/nice-auto-ml:apply")
#/serving/segment/nice-auto-ml/apply
@app.post("/serving/segment/nice-auto-ml/apply")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_apply_nice_auto_ml(request: Request, body: ApplyNiceAutoML):
    app_state = request.app.state
    app_config = app_state.config
    json_obj = await request.json()

    # TODO userid, companyCode
    user_id = "tester"  # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
    company_code = "Sv"  # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

    # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
    json_obj["UserId"] = user_id
    json_obj["CompanyCode"] = company_code

    # TODO faf
    file_name_key = str(uuid4())
    json_obj["FireAndForgetResultFileName"] = 'result_' + file_name_key
    json_obj["FireAndForgetErrorFileName"] = 'error_' + file_name_key
    json_obj["FireAndForgetDoneFileName"] = 'done_' + file_name_key

    (
        result_file_path_faf,
        error_file_path_faf,
        done_file_path_faf,
    ) = common_utils.prepare_fire_and_forget_from_json(app_config["ROOT_DIR"], json_obj)

    try:
        async with _get_current_process_lock(app_config):
            service_db_info = db_utils.get_service_db_info_from_app(app_config)
            exec_func = functools.partial(
                automl_executor.apply_nice_auto_ml,
                # company_db_info=company_db_info,
                service_db_info=service_db_info,
                file_server_host=app_config["FILE_SERVER_HOST"],
                file_server_port=app_config["FILE_SERVER_PORT"],
                h2o_file_server_host=app_config["H2O_FILE_SERVER_HOST"],
                h2o_file_server_port=app_config["H2O_FILE_SERVER_PORT"],
                numpy_use_32bit_float_precision=app_config["NUMPY_USE_32BIT_FLOAT_PRECISION"],
                result_file_path_faf=result_file_path_faf,
                done_file_path_faf=done_file_path_faf,
                h2o_host=app_config["SERVING_H2O_SERVER_HOST"],
                h2o_port=_get_next_h2o_port(app_config),
                h2o_older_version_port=app_config["H2O_OLDER_VERSION_PORT"],
                root_dir=app_config["ROOT_DIR"],
                json_obj=json_obj,
            )

            await asyncio.to_thread(exec_func)

            return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        with open(error_file_path_faf, "w") as efd, open(
            done_file_path_faf, "w"
        ) as dfd:
            efd.write(str(e))
            dfd.write(constants.FAF_ERROR_STRING)
        raise


#/serving/segment/nice-auto-ml/predict
@app.post("/serving/segment/nice-auto-ml/predict")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_predict_fit_nice_auto_ml(request: Request, body: str = Body(media_type="text/plain")):
    app_state = request.app.state
    app_config = app_state.config
    json_obj = await request.json()

    # TODO faf
    file_name_key = str(uuid4())
    json_obj["FireAndForgetResultFileName"] = 'result_' + file_name_key
    json_obj["FireAndForgetErrorFileName"] = 'error_' + file_name_key
    json_obj["FireAndForgetDoneFileName"] = 'done_' + file_name_key

    # TODO userid, companyCode
    json_obj["UserId"] = "tester"
    json_obj["CompanyCode"] = "Sv"

    (
        result_file_path_faf,
        error_file_path_faf,
        done_file_path_faf,
    ) = common_utils.prepare_fire_and_forget_from_json(app_config["ROOT_DIR"], json_obj)

    try:
        async with _get_current_process_lock(app_config):
            service_db_info = db_utils.get_service_db_info_from_app(app_config)
            exec_func = functools.partial(
                automl_executor.predict_nice_auto_ml,
                service_db_info=service_db_info,
                file_server_host=app_config["FILE_SERVER_HOST"],
                file_server_port=app_config["FILE_SERVER_PORT"],
                h2o_file_server_host=app_config["H2O_FILE_SERVER_HOST"],
                h2o_file_server_port=app_config["H2O_FILE_SERVER_PORT"],
                numpy_use_32bit_float_precision=app_config["NUMPY_USE_32BIT_FLOAT_PRECISION"],
                result_file_path_faf=result_file_path_faf,
                done_file_path_faf=done_file_path_faf,
                h2o_host=app_config["SERVING_H2O_SERVER_HOST"],
                h2o_port=_get_next_h2o_port(app_config),
                h2o_older_version_port=app_config["H2O_OLDER_VERSION_PORT"],
                root_dir=app_config["ROOT_DIR"],
                json_obj=json_obj,
            )

            await asyncio.to_thread(exec_func)

            return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        with open(error_file_path_faf, "w") as efd, open(
            done_file_path_faf, "w"
        ) as dfd:
            efd.write(str(e))
            dfd.write(constants.FAF_ERROR_STRING)
        raise


#/serving/segment/nice-auto-ml/history_properties
@app.get("/serving/segment/nice-auto-ml/history_properties")
# # @app.post('/get/stg_history')
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_stg_history_properties(request: Request, task_id: int = Query(alias="task-id")):
    app_state = request.app.state
    app_config = app_state.config
    try:
        task_id = int(request.query_params["task-id"])
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # TODO keycloak 에서 user_id, company_code 설정
        company_code = "Sv"
        user_id = "tester"

        exec_func = functools.partial(
            automl_executor.get_stg_history_properties,
            service_db_info=service_db_info,
            company_code=company_code,
            task_id=task_id,
        )

        stg_history_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(stg_history_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment/nice-auto-ml/available
@app.get('/serving/segment/nice-auto-ml/available')
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_automl_available_segments(request: Request, product_id: int = Query(alias="product-id")):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        product_id = request.query_params['product-id']
        # user_id = request.query_params['user-id']

        # TODO user_id 는 keycloak 통해서 세팅
        user_id = "tester"
        company_code = "Sv"

        exec_func = functools.partial(
            automl_executor.get_automl_available_segments,
            service_db_info=service_db_info,
            company_code=company_code,
            product_id=product_id,
            user_id = user_id,
        )

        long_task_status = await asyncio.to_thread(exec_func)

        return web_utils.json_response(long_task_status)

    except Exception as e:
        app_config['ERROR_LOGGER'].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment/predict
@app.post("/serving/segment/predict")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_predict_segment(request: Request, body: PredictSegment):
    app_state = request.app.state
    app_config = app_state.config
    json_obj = await request.json()

    # TODO keycloak 에서 user_id, company_code 설정
    json_obj["UserId"] = "tester"  # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
    json_obj["CompanyCode"] = "Sv"  # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

    # file_name_key = str(uuid4())
    # json_obj["FireAndForgetResultFileName"] = 'result_' + file_name_key
    # json_obj["FireAndForgetErrorFileName"] = 'error_' + file_name_key
    # json_obj["FireAndForgetDoneFileName"] = 'done_' + file_name_key
    #
    # (
    #     result_file_path_faf,
    #     error_file_path_faf,
    #     done_file_path_faf,
    # ) = common_utils.prepare_fire_and_forget_from_json(app_config["ROOT_DIR"], json_obj)

    try:
        async with _get_current_process_lock(app_config):
            service_db_info = db_utils.get_service_db_info_from_app(app_config)

            exec_func = functools.partial(
                segment_executor.predict_segment,
                service_db_info=service_db_info,
                file_server_host=app_config["FILE_SERVER_HOST"],
                file_server_port=app_config["FILE_SERVER_PORT"],
                h2o_script_obj=app_config["H2O_SCRIPT_OBJ"],
                r_script_obj=app_config["R_SCRIPT_OBJ"],
                numpy_use_32bit_float_precision=app_config["NUMPY_USE_32BIT_FLOAT_PRECISION"],
                # result_file_path_faf=result_file_path_faf,
                # error_file_path_faf=error_file_path_faf,
                # done_file_path_faf=done_file_path_faf,
                h2o_file_server_host=app_config["H2O_FILE_SERVER_HOST"],
                h2o_file_server_port=app_config["H2O_FILE_SERVER_PORT"],
                h2o_host=app_config["SERVING_H2O_SERVER_HOST"],
                h2o_port=app_config["SERVING_H2O_SERVER_PORT"],
                h2o_older_version_port=app_config["H2O_OLDER_VERSION_PORT"],
                json_obj=json_obj,
                app_config=app_config,
            )

            await asyncio.to_thread(exec_func)

            return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        # with open(error_file_path_faf, "w") as efd, open(
        #     done_file_path_faf, "w"
        # ) as dfd:
        #     efd.write(str(e))
        #     dfd.write(constants.FAF_ERROR_STRING)
        # raise
        raise Exception(str(e))


#/serving/segment/fine-classing/run
@app.post("/serving/segment/fine-classing/run")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_run_fine_classing(request: Request, body: GetFineClassingReport):
    app_state = request.app.state
    app_config = app_state.config
    json_obj = await request.json()

    # TODO keycloak 통해 처리
    json_obj["UserId"] = "tester"  # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
    json_obj["CompanyCode"] = "Sv"  # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

    file_name_key = str(uuid4())
    json_obj["FireAndForgetResultFileName"] = 'result_' + file_name_key
    json_obj["FireAndForgetErrorFileName"] = 'error_' + file_name_key
    json_obj["FireAndForgetDoneFileName"] = 'done_' + file_name_key

    (
        result_file_path_faf,
        error_file_path_faf,
        done_file_path_faf,
    ) = common_utils.prepare_fire_and_forget_from_json(app_config["ROOT_DIR"], json_obj)

    try:
        async with _get_current_process_lock(app_config):
            service_db_info = db_utils.get_service_db_info_from_app(app_config)
            exec_func = functools.partial(
                segment_executor.run_fine_classing,
                service_db_info=service_db_info,
                file_server_host=app_config["FILE_SERVER_HOST"],
                file_server_port=app_config["FILE_SERVER_PORT"],
                root_dir=app_config["ROOT_DIR"],
                numpy_use_32bit_float_precision=app_config["NUMPY_USE_32BIT_FLOAT_PRECISION"],
                result_file_path_faf=result_file_path_faf,
                done_file_path_faf=done_file_path_faf,
                json_obj=json_obj,
            )

            await asyncio.to_thread(exec_func)

            return web_utils.empty_response()
