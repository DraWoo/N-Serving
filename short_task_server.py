####################################################################################################
# setup
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

        server_dir_name_list = [
            constants.SERVER_REPOSITORY_NAME,
            constants.APP_UPDATE_DIR_NAME,
            constants.CLIENT_POLLING_DIR_NAME,
        ]
        for server_dir_name in server_dir_name_list:
            dir_path = os.path.join(app.state.config["ROOT_DIR"], server_dir_name)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

        yield

    except Exception as e:
        raise Exception(str(e))

security = HTTPBearer(auto_error=False)
# app def
app = FastAPI(lifespan=lifespan, docs_url=None, dependencies=[Depends(security)])


####################################################################################################
#========================================= swagger ui setting ======================================#
####################################################################################################
# static 폴더
app.mount(path="/static", StaticFiles(directory=f"{os.path.dirname(os.path.abspath(__file__))}/static"), name="static")

# swagger ui 로컬 정적 파일로 제공
#/docs
@app.get(path="/docs", include_in_schema=False)
def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="test",
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
        # swagger_ui_preset_url="/static/swagger-ui-standalone-preset.js",
    )


####################################################################################################
#======================================= internal function ========================================#
####################################################################################################

def _get_current_process_lock(app: {_getitem_}):
    app_pid = os.getpid()
    if app_pid not in app["PROCESS_LOCK_DICT"]:
        app["PROCESS_LOCK_DICT"][app_pid] = asyncio.Lock()

    return app["PROCESS_LOCK_DICT"][app_pid]


def _h2o_health_check(h2o_host, h2o_port, h2o_timeout):
    # when h2o.init, it doesn't require scheme
    concat_h2o_url = "http://" + web_utils.concat_host_and_port(h2o_host, h2o_port)
    try:
        return (
            urllib.request.urlopen(concat_h2o_url, timeout=h2o_timeout).getcode() == 200
        )
    except urllib.error.URLError:
        return False


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
    return -1


def _get_next_h2o_port(app: {_getitem_}):
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


####################################################################################################
#============================================ handlers ============================================#
####################################################################################################
@app.middleware("http")
async def set_access_logger(request: Request, call_next):

    request.state.request_id = request_id

    # TODO keycloak 설정 후 keycloak 사용자 이름 받도록 수정
    user_id = "tester"
    client_ip = request.client.host if request.client else "unknown"
    try:
        response = await call_next(request)
    except Exception:
        duration = (time.perf_counter() - start_time)*1000

        access_logger.exception(
            msg: "Unexpected middleware failure | request_id=%s user_id=%s method=%s path=%s client_ip=%s duration_ms=%.2f",
            *args: request_id,
            user_id,
            request.method,
            request.url.path,
            client_ip,
            duration
        )
        raise

    duration = (time.perf_counter() - start_time)*1000
    route = request.scope.get("route")
    endpoint = (
        route.endpoint.__name__
        if route and hasattr(route, "endpoint")
        else "-"
    )
    access_logger.info(
        msg: "request_id=%s user_id=%s method=%s endpoint=%s path=%s status=%d duration_ms=%.2f client_ip=%s",
        *args: request_id,
        user_id,
        request.method,
        endpoint,
        request.url.path,
        response.status_code,
        duration,
        client_ip
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    422 Unprocessable Entity error 해결 시 raw body 확인을 위해 추가
    """
    print(f"invalid data: {exc.body}")
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": exc.errors(), "body": exc.body})
    )


####################################################################################################
#============================================ api start ============================================#
####################################################################################################
#/serving/product-list
@app.get("/serving/product-list")
@web_utils.web_err_handler
@web_utils.auth_handler
# @app.exception_handler(RequestValidationError)
async def serving_get_product_list(request: Request):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # product_id = request.query_params["product-id"]
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        # TODO keycloak 통해 처리
        user_id = app_config["auth_info"]["preferred_username"]
        user_role = app_config["auth_info"]["resource_access"]["account"]["roles"]
        user_grp = app_config["auth_info"]["grp"]
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        exec_func = functools.partial(
            serving_product_executor.get_product_list,
            service_db_info=service_db_info,
            # product_id=product_id,
            # user_id=user_id,
            # company_code=company_code,
        )

        product_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(product_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product
@app.post("/serving/product")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_add_product(request: Request, files: list[UploadFile] = File(None),
                              product: str = Form(), segments: str = Form(), models: str = Form()):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # json_obj = await request.json() # 모형 파일 스트림 으로 받기 위해 form-data 처리
        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        reader = await request.form()
        product_json_str, segment_json_str, temp_model_files = None, None, {}

        product_json_str = reader['product']
        json_obj = json.loads(product_json_str)

        segment_json_str = reader['segments']
        json_obj["Segments"] = json.loads(segment_json_str)

        files = reader.getlist('files')

        models_json_str = reader['models']
        models = json.loads(models_json_str)

        for i, model_file in enumerate(files):
            temp_model_file_path = common_utils.make_temp_file()
            with open(temp_model_file_path, "wb") as f:
                while True:
                    chunk = await model_file.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
            temp_model_files[models[i]] = temp_model_file_path

        # TODO keycloak 통해 처리
        json_obj["UserId"] = "tester" # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv" # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["Segments"] = json.loads(segment_json_str)

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        for seg_json_obj in json_obj["Segments"]:
            seg_json_obj["UserId"] = json_obj["UserId"]
            seg_json_obj["CompanyCode"] = json_obj["CompanyCode"]
            for model_json_obj in seg_json_obj['Models']:
                model_json_obj["UserId"] = json_obj['UserId']
                model_json_obj["CompanyCode"] = json_obj['CompanyCode']
                model_json_obj["TempFileName"] = ""
                if model_json_obj["ModelId"] in temp_model_files:
                    model_json_obj["TempFileName"] = temp_model_files[model_json_obj["ModelId"]]

        exec_func = functools.partial(
            serving_product_executor.add_product,
            company_db_info=company_db_info,
            file_server=app_config["FILE_SERVER"],
            h2o_server=app_config["H2O_SERVER"],
            json_obj=json_obj,
            root_dir=app_config["ROOT_DIR"]
        )

        result_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(result_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product
@app.delete("/serving/product")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_delete_product(request: Request, product_id: int = Query(alias='product-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        product_id = request.query_params["product-id"]

        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_product_executor.delete_product,
            service_db_info=service_db_info,
            user_id=user_id,
            company_code=company_code,
            product_id=product_id,
            file_server=app_config["FILE_SERVER"]
        )

        result_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(result_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/detail
@app.put("/serving/product/detail")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_modify_product_detail(request: Request, body: ModifyProductBody, product_id: int = Query(alias='product-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        product_id = request.query_params["product-id"]

        json_obj["UserId"] = "tester" # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv" # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_product_executor.modify_product_detail,
            product_id=product_id,
            company_db_info=company_db_info,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/mart
@app.get("/serving/product/mart")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_product_mart(request: Request, product_id: int = Query(alias='product-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        product_id = request.query_params["product-id"]
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        exec_func = functools.partial(
            serving_product_executor.get_product_mart_list,
            service_db_info=service_db_info,
            product_id=product_id,
            user_id=user_id,
            company_code=company_code,
        )

        mart_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(mart_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/mart/local-upload
@app.post("/serving/product/mart/local-upload")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_mart_local_upload(request: Request, meta: str = Form(), file: list[UploadFile] = File()):
    app_state = request.app.state
    app_config = app_state.config
    try:
        reader = await request.form()
        # 1. JSON
        json_str = reader['meta']
        json_obj = json.loads(json_str)
     
    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))

    # TODO 파일명 생성로직 추가
    file_name_key = str(uuid4())
    result_file_path_faf = 'result_' + file_name_key
    error_file_path_faf = 'error_' + file_name_key
    done_file_path_faf = 'done_' + file_name_key

    # TODO keycloak 통해 처리
    user_id = "tester"
    company_code = "Sv"

    try:
        async with _get_current_process_lock(app_config):
            # 2. DATA
            raw_mart_file_path = common_utils.make_temp_file()
            files = reader.getlist('file')
            for data in files:
                with open(raw_mart_file_path, "wb") as raw_mart_fd:
                    CHUNK_SIZE = 2 ** 20
                    while True:
                        data_bytes = await data.read(CHUNK_SIZE)
                        if not data_bytes:
                            break
                        raw_mart_fd.write(data_bytes)

            service_db_info = db_utils.get_service_db_info_from_app(app_config)
            company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
            company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

            exec_func = functools.partial(
                serving_product_executor.upload_data_from_server,
                company_db_info=company_db_info,
                company_code=company_code,
                user_id=user_id,
                result_file_path_faf=result_file_path_faf,
                done_file_path_faf=done_file_path_faf,
                meta_json=json_obj,
                root_dir=app_config["ROOT_DIR"],
                file_server_host=app_config["FILE_SERVER_HOST"],
                file_server_port=app_config["FILE_SERVER_PORT"],
            )

            mart_list_json = await asyncio.to_thread(exec_func)

            return web_utils.json_response(mart_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        with open(error_file_path_faf, "w") as efd, open(
            done_file_path_faf, "w"
        ) as dfd:
            efd.write(str(e))
            dfd.write(constants.FAF_ERROR_STRING)
        raise Exception(str(e))


#/serving/product/mart/server-upload
@app.post("/serving/product/mart/server-upload")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_mart_server_upload(request: Request, body: MartServerUpload):
    app_state = request.app.state
    app_config = app_state.config

    file_name_key = str(uuid4())
    result_file_path_faf = 'result_' + file_name_key
    error_file_path_faf = 'error_' + file_name_key
    done_file_path_faf = 'done_' + file_name_key

    try:
        json_obj = await request.json()

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        company_code = company_code,
        user_id = user_id,
        root_dir = app_config["ROOT_DIR"],
        result_file_path_faf = result_file_path_faf,
        done_file_path_faf = done_file_path_faf,
        meta_json = json_obj,
        raw_mart_file_path = raw_mart_file_path,
        file_server_host = app_config["FILE_SERVER_HOST"],
        file_server_port = app_config["FILE_SERVER_PORT"],
        external_purpose = app_config["EXTERNAL_PURPOSE"],
        )
        await asyncio.to_thread(exec_func)
        os.remove(raw_mart_file_path)
        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        with open(error_file_path_faf, "w") as efd, open(
            done_file_path_faf, "w"
        ) as dfd:
            efd.write(str(e))
            dfd.write(constants.FAF_ERROR_STRING)
        raise Exception(str(e))


#/serving/product/mart/query-upload
@app.post("/serving/product/mart/query-upload")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_mart_query_upload(request: Request, body: MartQueryUpload):
    app_state = request.app.state
    app_config = app_state.config

    file_name_key = str(uuid4())
    result_file_path_faf = 'result_' + file_name_key
    error_file_path_faf = 'error_' + file_name_key
    done_file_path_faf = 'done_' + file_name_key

    try:
        json_obj = await request.json()

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

company_code = “Sv”
service_db_info = db_utils.get_service_db_info_from_app(app_info)

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_product_executor.update_product_feature,
            company_db_info=company_db_info,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/feature
@app.delete("/serving/product/feature")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_delete_product_feature(request: Request, body: ProductFeature):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_product_executor.delete_product_feature,
            company_db_info=company_db_info,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


## 항목 정보 다운로드를 위해 신규 추가
#/serving/product/feature/file
@app.post("/serving/product/feature/file")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_download_product_feature_file(request: Request, body: DownloadProductFeatureFile):
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

        product_id = json_obj["ProductId"]

        exec_func = functools.partial(
            serving_product_executor.get_feature_json,
            company_db_info=company_db_info,
            product_id=product_id,
        )
        product_var_list_json, headers = await asyncio.to_thread(exec_func)

        headers = {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f'attachment; filename="{product_id}_features.csv"',
            "Cache-Control": "no-cache",
        }

        def _generator(product_var_list_json, headers):
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            writer.writerow(headers)
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate(0)

            for row_json in product_var_list_json:
                writer.writerow([row_json.get(h, "") for h in headers])
                yield buffer.getvalue().encode("utf-8")
                buffer.seek(0)
                buffer.truncate(0)

        return StreamingResponse(_generator(product_var_list_json, headers), status_code=200, headers=headers)

        # return await web_utils.chunked_remote_file_response(excel_file_url, request)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/feature/group-list
@app.get("/serving/product/feature/group-list")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_product_feature_group_list(request: Request, product_id: int = Query(alias="product-id")):
    app_state = request.app.state
    app_config = app_state.config
    try:
        product_id = request.query_params["product-id"]
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        exec_func = functools.partial(
            serving_product_executor.get_product_feature_group_list,
            service_db_info=service_db_info,
            product_id=product_id,
            company_code=company_code,
        )

        feature_grp_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(feature_grp_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/feature/group
@app.get("/serving/product/feature/group")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_product_feature_group(request: Request, feature_grp_id: int = Query(alias="feature-group-id")):
    app_state = request.app.state
    app_config = app_state.config
    try:
        feature_grp_id = request.query_params["feature-group-id"]
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        exec_func = functools.partial(
            serving_product_executor.get_product_feature_group_var,
            service_db_info=service_db_info,
            company_code=company_code,
            feature_grp_id=feature_grp_id,
        )

        feature_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(feature_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/feature/group
@app.post("/serving/product/feature/group")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_add_product_feature_group(request: Request, body: AddProductFeatureGroup):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        exec_func = functools.partial(
            serving_product_executor.add_product_feature_grp,
            service_db_info=service_db_info,
            json_obj=json_obj,
        )

        result_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(result_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/feature/group
@app.put("/serving/product/feature/group")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_modify_product_feature(request: Request, body: ModifyProductFeature):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        exec_func = functools.partial(
            serving_product_executor.save_product_feature_grp,
            service_db_info=service_db_info,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/feature/group
@app.delete("/serving/product/feature/group")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_delete_product_feature_group(request: Request, body: DeleteProductFeatureGroup):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        exec_func = functools.partial(
            serving_product_executor.delete_product_feature_grp,
            service_db_info=service_db_info,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/feature/group/{FeatureGroupId}
@app.post("/serving/product/feature/group/{FeatureGroupId}")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_add_product_feature_in_group(request: Request, body: FeatureInGroup, feature_group_id: int = Path(alias="FeatureGroupId")):
    app_state = request.app.state
    app_config = app_state.config
    try:
        feature_group_id = int(request.path_params["FeatureGroupId"])
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_product_executor.add_product_feature_in_grp,
            company_db_info=company_db_info,
            feature_group_id=feature_group_id,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


## 항목 정보 다운로드를 위해 신규 추가
#/serving/product/feature/group/file/{FeatureGroupId}
@app.post("/serving/product/feature/group/file/{FeatureGroupId}")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_download_product_feature_group_file(request: Request, body: DownloadProductFeatureFile, feature_group_id: int = Path(alias="FeatureGroupId")):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        feature_group_id = int(request.path_params["FeatureGroupId"])

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        product_id = json_obj["ProductId"]

        exec_func = functools.partial(
            serving_product_executor.get_feature_grp_json,
            company_db_info=company_db_info,
            product_id=product_id,
            product_var_grp_id=feature_group_id,
        )

        product_var_list_json, headers = await asyncio.to_thread(exec_func)
        headers = {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f'attachment; filename="{product_id}_{feature_group_id}_features.csv"',
            "Cache-Control": "no-cache",
        }

        def _generator(product_var_list_json, headers):
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            writer.writerow(headers)
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate(0)

            for row_json in product_var_list_json:
                writer.writerow([row_json.get(h, "") for h in headers])
                yield buffer.getvalue().encode("utf-8")
                buffer.seek(0)
                buffer.truncate(0)

        return StreamingResponse(_generator(product_var_list_json, headers), status_code=200, headers=headers)

        # return await web_utils.chunked_remote_file_response(excel_file_url, request)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/feature/group/{FeatureGroupId}
@app.put("/serving/product/feature/group/{FeatureGroupId}")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_update_product_feature_in_group(request: Request, body: FeatureInGroup, feature_group_id: int = Path(alias="FeatureGroupId")):
    app_state = request.app.state
    app_config = app_state.config
    try:
        feature_group_id = int(request.path_params["FeatureGroupId"])

        json_obj = await request.json()

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_product_executor.update_product_feature_in_grp,
            feature_group_id=feature_group_id,
            company_db_info=company_db_info,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)
        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/feature/group/{FeatureGroupId}
@app.delete("/serving/product/feature/group/{FeatureGroupId}")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_delete_product_feature_in_group(request: Request, body: DeleteProductFeatureInGroup, feature_group_id: int = Path(alias="FeatureGroupId")):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        feature_group_id = int(request.path_params["FeatureGroupId"])

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_product_executor.delete_product_feature_in_grp,
            company_db_info=company_db_info,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/column
@app.put("/serving/product/column")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_product_modify_column(request: Request, body: ModifyProductColumn):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        json_obj["UserId"] = "tester"  # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"  # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_product_executor.modify_product_column,
            company_db_info=company_db_info,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/detail
@app.get("/serving/product/detail")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_product_detail(request: Request, product_id: int = Query(alias='id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # product_id = request.path_params["product_id"]
        product_id = request.query_params["id"]

        user_id = "tester"
        company_code = "Sv"

        exec_func = functools.partial(
            serving_product_executor.get_product_detail,
            service_db_info=service_db_info,
            product_id=product_id,
            company_code=company_code,
        )

        product_detail_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(product_detail_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/history
@app.get("/serving/product/history")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_product_history_list(request: Request, product_id: int = Query(alias='id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # product_id = request.path_params["product_id"]
        product_id = request.query_params["id"]

        user_id = "tester"
        company_code = "Sv"

        exec_func = functools.partial(
            serving_product_executor.get_product_history_list,
            service_db_info=service_db_info,
            product_id=product_id,
            company_code=company_code,
        )

        product_history_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(product_history_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/history/detail/{product_history_id}
@app.get("/serving/product/history/detail/{product_history_id}")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_product_history_details(request: Request, product_history_id: int = Path(alias='product_history_id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        product_history_id = request.path_params['product_history_id']

        user_id = "tester"
        company_code = "Sv"

        exec_func = functools.partial(
            serving_product_executor.get_product_history_details,
            service_db_info=service_db_info,
            product_history_id=product_history_id,
            company_code=company_code,
        )

        product_detail_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(product_detail_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


# TODO - 작성 필요
#/serving/base-ym-list
@app.get("/serving/base-ym-list")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_base_yn_list(request: Request, product_id: int = Query(alias='id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # auth_key = request.query_params["auth-key"]
        product_id = int(request.query_params["id"])

        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_product_executor.get_base_ym_list,
            service_db_info=service_db_info,
            # auth_key=auth_key,
            product_id=product_id,
            company_code=company_code,
        )

        base_ym_list = await asyncio.to_thread(exec_func)

        return web_utils.json_response(base_ym_list)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/report/segment/perf-history-list
@app.post("/serving/report/segment/perf-history-list")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_segment_perf_history_list(request: Request, body: GetSegmentPerfHistoryList):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = "tester"
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"

        # auth_key = request.query_params["auth-key"]
        # segment_id = int(request.query_params["segment-id"])
        # base_only = bool(int(request.query_params["base-only"]))
        # segment_flag = int(request.query_params.get("segment-flag", "-1"))

        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_product_executor.get_segment_perf_history_list,
            service_db_info=service_db_info,
            # auth_key=auth_key,
            # segment_id=segment_id,
            # base_only=base_only,
            # segment_flag=segment_flag,
            # company_code=company_code,
            json_obj=json_obj,
        )

        perf_history_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(perf_history_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/task-list
@app.get("/serving/product/task-list")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_product_task_list(request: Request,
                                     product_name: str | None = Query(default=None, alias='product-name'),
                                     task_type: str | None = Query(default=None, alias='task-type'),
                                     status: str | None = Query(default=None, alias='status'),
                                     executor_id: str | None = Query(default=None, alias='executor_id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        product_name = request.query_params.get("product-name")
        task_type = request.query_params.get("task-type")
        status = request.query_params.get("status")
        executor_id = request.query_params.get("executor_id")

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # TODO keycloak 통해서 설정
        user_id = "tester"  # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        company_code = "Sv"  # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

        # TODO 보기 권한 설정 필요: 사용자 id 단위/그룹 단위

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_product_executor.get_product_task_list,
            company_db_info=company_db_info,
            product_name=product_name,
            task_type=task_type,
            status=status,
            executor_id=executor_id,
        )

        task_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(task_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/product/task-list/error/{TaskId}
@app.get("/serving/product/task-list/error/{TaskId}")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_product_task_error(request: Request, task_id: int = Path(alias='TaskId')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        task_id = request.path_params["TaskId"]

        # TODO keycloak 통해서 설정
        user_id = "tester"  # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        company_code = "Sv"  # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_product_executor.get_product_task_error,
            company_db_info=company_db_info,
            task_id=task_id
        )

        task_error_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(task_error_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment/segment-list
@app.get("/serving/segment/segment-list")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_segment_list(request: Request, product_id: int = Query(alias='id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # product_id = request.path_params["product_id"]
        product_ids = request.query_params["id"]

        user_id = "tester"
        company_code = "Sv"

        exec_func = functools.partial(
            serving_product_executor.get_segment_list,
            service_db_info=service_db_info,
            product_ids=product_ids,
            company_code=company_code,
        )

        segment_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(segment_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment
@app.post("/serving/segment")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_add_segment(request: Request, productId: str = Form(), segment: str = Form(),
                              files: list[UploadFile] = File(None), models: str = Form()):
    """
    : 기존 Product 에 신규 Segment 추가
    """

    app_state = request.app.state
    app_config = app_state.config
    try:
        # json_obj = await request.json() # 모형 파일 스트림 으로 받기 위해 form-data 처리
        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        reader = await request.form()
        product_json_str, segment_json_str, temp_model_files = None, None, {}

        product_json_str = reader['productId']
        json_obj = json.loads(product_json_str)

        segment_json_str = reader['segment']
        json_obj["Segments"] = json.loads(segment_json_str)

        files = reader.getlist('files')

        models_json_str = reader['models']
        models = json.loads(models_json_str)

        for i, model_file in enumerate(files):
            temp_model_file_path = common_utils.make_temp_file()
            with open(temp_model_file_path, "wb") as f:
                while True:
                    chunk = await model_file.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
            temp_model_files[models[i]] = temp_model_file_path  # 나중에 테스트 필요

        json_obj["UserId"] = "tester"  # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv"  # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        for model_json_obj in json_obj["Segments"]["Models"]:
            model_json_obj["UserId"] = json_obj["UserId"]
            model_json_obj["CompanyCode"] = json_obj["CompanyCode"]
            model_json_obj["TempFileName"] = ""
            if model_json_obj["ModelId"] in temp_model_files:
                model_json_obj["TempFileName"] = temp_model_files[model_json_obj["ModelId"]]

        exec_func = functools.partial(
            serving_segment_executor.add_segment_one,
            company_db_info=company_db_info,
            file_server=app_config["FILE_SERVER"],
            h2o_server=app_config["H2O_SERVER"],
            json_obj=json_obj,
            root_dir=app_config["ROOT_DIR"]
        )

        product_detail_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(product_detail_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment
@app.put("/serving/segment")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_modify_segment(request: Request, productId: str = Form(), segment: str = Form(),
                                 files: list[UploadFile] = File(None), models: str = Form()):
    """
    : 기존 Product 내 기존 Segment 수정
    """
    app_state = request.app.state
    app_config = app_state.config
    try:
        # json_obj = await request.json() # 모형 파일 스트림 으로 받기 위해 form-data 처리
        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        reader = await request.form()
        product_json_str, segment_json_str, temp_model_files = None, None, {}

        product_json_str = reader['productId']
        json_obj = json.loads(product_json_str)

        segment_json_str = reader['segment']
        json_obj["Segments"] = json.loads(segment_json_str)

        files = reader.getlist('files')

        models_json_str = reader['models']
        models = json.loads(models_json_str)

        for i, model_file in enumerate(files):
            temp_model_file_path = common_utils.make_temp_file()
            with open(temp_model_file_path, "wb") as f:
                while True:
                    chunk = await model_file.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
            temp_model_files[models[i]] = temp_model_file_path

        json_obj["UserId"] = "tester" # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv" # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        for model_json_obj in json_obj["Segments"]["Models"]:
            model_json_obj["UserId"] = json_obj["UserId"]
            model_json_obj["CompanyCode"] = json_obj["CompanyCode"]
            model_json_obj["TempFileName"] = ""
            if model_json_obj["ModelId"] in temp_model_files:
                model_json_obj["TempFileName"] = temp_model_files[model_json_obj["ModelId"]]

        exec_func = functools.partial(
            serving_segment_executor.modify_segment,
            company_db_info=company_db_info,
            file_server=app_config["FILE_SERVER"],
            h2o_server=app_config["H2O_SERVER"],
            json_obj=json_obj,
            root_dir=app_config["ROOT_DIR"]
        )

        product_detail_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(product_detail_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment/detail
@app.put("/serving/segment/detail")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_modify_segment_detail(request: Request, body: ModifySegmentDetail):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()
        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        json_obj["UserId"] = "tester" # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["CompanyCode"] = "Sv" # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, json_obj["CompanyCode"])
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_segment_executor.modify_segment_detail,
            company_db_info=company_db_info,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment
@app.delete("/serving/segment")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_delete_segment(request: Request, body: DeleteSegment):
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()

        product_id = int(json_obj["ProductId"])
        segment_id = int(json_obj["SegmentId"])
        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        user_id = "tester" # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        company_code = "Sv" # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_segment_executor.delete_segment,
            company_db_info=company_db_info,
            company_code=company_code,
            product_id=product_id,
            segment_id=segment_id,
            file_server=app_config["FILE_SERVER"],
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        


# 실행결과가 아닌 히스토리에서 조회중인 히스토리 엑셀 파일 다운로드
#/serving/product/fine-classing/history/excel-file
@app.get("/serving/product/fine-classing/history/excel-file")
@web_utils.web_err_handler
# @web_utils.auth_handler
async def serving_get_segment_fine_classing_result_download(request: Request,
                                                            product_id: int = Query(alias='product-id'),
                                                            history_id: int = Query(alias='history-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_segment_executor.get_fine_classing_history_excel_file_url,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            product_id=product_id,
            history_id=history_id,
        )
        excel_file_url = await asyncio.to_thread(exec_func)

        return await web_utils.chunked_remote_file_response(excel_file_url, request)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


### FC 실행 결과 조회 위해 신규 추가(기존 API 발견되면 해당 내용 이용하여 변경 필요)
# 실행 결과를 가져오기 위한 API (히스토리가 아님)
#/serving/product/fine-classing/result
@app.get("/serving/product/fine-classing/result")
@web_utils.web_err_handler
# @web_utils.auth_handler
async def serving_get_segment_fine_classing_result(request: Request, product_id: int = Query(alias='product-id'),
                                                     task_id: int = Query(alias='task-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        load_result_func = functools.partial(
            serving_segment_executor.get_fine_classing_result,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            product_id=product_id,
            task_id=task_id,
        )

        fc_result_json = await asyncio.to_thread(load_result_func)

        # return await web_utils.chunked_remote_file_response(fc_result_json, request)
        return web_utils.json_response(fc_result_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


## 결과 파일 다운로드를 위해 신규 추가(기존 API 발견되면 해당 내용 이용하여 변경 필요)
#/serving/product/fine-classing/result-download
@app.get("/serving/product/fine-classing/result-download")
@web_utils.web_err_handler
# @web_utils.auth_handler
async def serving_get_fine_classing_result_download(request: Request,
                                                     product_id: int = Query(alias='product-id'),
                                                     task_id: int = Query(alias='task-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_segment_executor.get_fine_classing_result_excel_file_url,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            product_id=product_id,
            task_id=task_id
        )
        result_file_url = await asyncio.to_thread(exec_func)

        return await web_utils.chunked_remote_file_response(result_file_url, request)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


# 차트 그리기를 위한 지표 조회
#/serving/product/fine-classing/performances
@app.get("/serving/product/fine-classing/performances")
@web_utils.web_err_handler
# @web_utils.auth_handler
async def serving_segment_get_fine_classing_performances(request: Request, product_id: int = Query(alias="product-id")):
    app_state = request.app.state
    app_config = app_state.config

    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        product_id = int(request.query_params["product-id"])

        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        exec_func = functools.partial(
            serving_segment_executor.get_fine_classing_history_performances,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            product_id=product_id,
        )

        perf_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(perf_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


# fineclassing 결과에서 히스토리로 저장
#/serving/product/fine-classing/save
@app.post("/serving/product/fine-classing/save")
@web_utils.web_err_handler
# @web_utils.auth_handler
async def serving_save_segment_fineclassing_result(request: Request, fc_result: SaveFineClassingResult):
    app_state = request.app.state
    app_config = app_state.config

    try:
        # TODO keycloak 통해 처리
        json_obj = {"UserId": "tester", "CompanyCode": "Sv"}

        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        exec_func = functools.partial(
            serving_segment_executor.save_fine_classing_history,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            fc_result=fc_result,
            json_obj=json_obj,
        )
        # None
        segment_columns = await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


# 히스토리 순서 저장
#/serving/product/fine-classing/history-order
@app.put("/serving/product/fine-classing/history-order")
@web_utils.web_err_handler
# @web_utils.auth_handler
async def serving_update_fine_classing_history_order(request: Request, fc_history_order: ProductHistoryOrder):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO keycloak 통해 처리
        json_obj = {"UserId": "tester", "CompanyCode": "Sv"}

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_segment_executor.update_fine_classing_history_order,
            service_db_info=service_db_info,
            fc_history_order=fc_history_order,
            json_obj=json_obj,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


# 선택 히스토리 삭제
#/serving/product/fine-classing/history
@app.delete("/serving/product/fine-classing/history")
@web_utils.web_err_handler
# @web_utils.auth_handler
async def serving_delete_fine_classing_history(request: Request, product_id: int = Query(alias="product-id"),
                                                history_id: int = Query(alias="history-id")):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_segment_executor.delete_fine_classing_history,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            product_id=product_id,
            history_id=history_id,
        )

        await asyncio.to_thread(exec_func)

        return web_utils.empty_response()

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment/refit-result-list
@app.get("/serving/segment/refit-result-list")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_refit_result_list(request: Request):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        product_id = request.query_params['product-id']

        # TODO user_id 는 keycloak 통해서 세팅
        user_id = "tester"
        company_code = "Sv"

        exec_func = functools.partial(
            serving_segment_executor.get_refit_result_list,
            service_db_info=service_db_info,
            company_code=company_code,
            product_id=product_id
        )

        refit_result_list = await asyncio.to_thread(exec_func)

        return web_utils.json_response(refit_result_list)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


## REFIT 실행 결과 조회 위해 신규 추가(기존 API 발견되면 해당 내용 이용하여 변경 필요)
# 실행 결과를 가져오기 위한 API (히스토리가 아님)
#/serving/segment/refit/result
@app.get("/serving/segment/refit/result")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_segment_refit_result(request: Request):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        product_id = request.query_params['product-id']
        task_id = request.query_params['task-id']
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        load_result_func = functools.partial(
            serving_segment_executor.get_refit_result,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            product_id=product_id,
            task_id=task_id,
        )

        refit_result_json = await asyncio.to_thread(load_result_func)

        # return await web_utils.chunked_remote_file_response(fc_result_json, request)
        return web_utils.json_response(refit_result_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


## 예측치산출 실행 결과 조회 위해 신규 추가(기존 API 발견되면 해당 내용 이용하여 변경 필요)
# 실행 결과를 가져오기 위한 API (히스토리가 아님)
#/serving/segment/predict/result
@app.get("/serving/segment/predict/result")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_segment_predict_result(request: Request, product_id: int = Query(alias='product-id'),
                                               task_id: int = Query(alias='task-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        product_id = request.query_params["product-id"]
        task_id = request.query_params["task-id"]
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        load_result_func = functools.partial(
            serving_segment_executor.get_predict_result,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            product_id=product_id,
            task_id=task_id,
        )

        predict_result_json = await asyncio.to_thread(load_result_func)

        # return await web_utils.chunked_remote_file_response(predict_result_json, request)
        return web_utils.json_response(predict_result_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


## 수행일시 가져오기 위해 신규 추가
#/serving/long-task
@app.get('/serving/long-task')
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_long_task_list(request: Request, product_id: int = Query(alias='product-id'),
                                  segment_id: str | None = Query(default=None, alias='segment-id'),
                                  task_type: str = Query(alias='task-type'),
                                  status: str = Query()):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        product_id = request.query_params['product-id']
        segment_id = request.query_params.get('segment-id')
        task_type = request.query_params['task-type']
        status = request.query_params['status']

        # TODO user_id 는 keycloak 통해서 세팅
        user_id = "tester"
        company_code = "Sv"

        exec_func = functools.partial(
            serving_segment_executor.get_long_task_list,
            service_db_info=service_db_info,
            company_code=company_code,
            product_id=product_id,
            segment_id=segment_id,
            task_type=task_type,
            status=status,
            user_id=user_id,
        )

        long_task_list = await asyncio.to_thread(exec_func)

        return web_utils.json_response(long_task_list)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/refit-result
@app.get('/serving/refit-result')
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_refit_result_list(request: Request):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        product_id = request.query_params['product-id']

        # TODO user_id 는 keycloak 통해서 세팅
        user_id = "tester"
        company_code = "Sv"

        exec_func = functools.partial(
            serving_segment_executor.get_refit_result_list,
            service_db_info=service_db_info,
            company_code=company_code,
            product_id=product_id
        )

        refit_result_list = await asyncio.to_thread(exec_func)

        return web_utils.json_response(refit_result_list)

    except Exception as e:
        app_config['ERROR_LOGGER'].error(traceback.format_exc())
        raise Exception(str(e))


## REFIT 실행 결과 조회 위해 신규 추가(기존 API 발견되면 해당 내용 이용하여 변경 필요)
# 실행 결과를 가져오기 위한 API (히스토리가 아님)
#/serving/segment/refit/result
@app.get("/serving/segment/refit/result")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_segment_refit_result(request: Request):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        # TODO param 정리
        product_id = request.query_params["product-id"]
        task_id = request.query_params["task-id"]
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        load_result_func = functools.partial(
            serving_segment_executor.get_refit_result,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            product_id=product_id,
            task_id=task_id,
        )

        refit_result_json = await asyncio.to_thread(load_result_func)

        # return await web_utils.chunked_remote_file_response(fc_result_json, request)
        return web_utils.json_response(refit_result_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


## 예측치산출 실행 결과 조회 위해 신규 추가(기존 API 발견되면 해당 내용 이용하여 변경 필요)
# 실행 결과를 가져오기 위한 API (히스토리가 아님)
#/serving/segment/predict/result
@app.get("/serving/segment/predict/result")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_segment_predict_result(request: Request, product_id: int = Query(alias='product-id'),
                                               task_id: int = Query(alias='task-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        product_id = request.query_params["product-id"]
        task_id = request.query_params["task-id"]
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        load_result_func = functools.partial(
            serving_segment_executor.get_predict_result,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            product_id=product_id,
            task_id=task_id,
        )

        predict_result_json = await asyncio.to_thread(load_result_func)

        # return await web_utils.chunked_remote_file_response(predict_result_json, request)
        return web_utils.json_response(predict_result_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/mart/columns
@app.get("/serving/mart/columns")
# @app.get('/mart/columns')
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_mart_columns(request: Request, mart_name: str = Query(alias='mart-name'),
                                    segment_id: int | None = Query(default=None, alias='segment-id'),
                                    include_var_info: int | None = Query(default=None, alias='include-var-info')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        mart_name = request.query_params["mart-name"]
        # [2022-05-30] syg - get flow target columns using flow id param
        if "segment-id" in request.query_params:
            segment_id = int(request.query_params["segment-id"])
        else:
            segment_id = -1
        if "include-var-info" in request.query_params:
            include_var_info = bool(int(request.query_params["include-var-info"]))
        else:
            include_var_info = False
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_product_executor.get_mart_columns,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            mart_name=mart_name,
            segment_id=segment_id,
            include_var_info=include_var_info,
        )

        mart_columns_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(mart_columns_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment/columns
@app.get("/serving/segment/columns")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_segment_column_names(request: Request, segment_id: int = Query(alias='segment-id')):
    app_state = request.app.state
    app_config = app_state.config

    try:
        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        segment_id = int(request.query_params["segment-id"])

        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        exec_func = functools.partial(
            serving_segment_executor.get_segment_columns,
            service_db_info=service_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            company_code=company_code,
            segment_id=segment_id,
        )

        segment_columns = await asyncio.to_thread(exec_func)

        return web_utils.json_response(segment_columns)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/segment/targets
@app.get("/serving/segment/targets")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_segment_target_columns(request: Request,
                                              segment_ids: list | None = Query(default=None, alias='segment-id'),
                                              segment_id: int | None = Query(default=None, alias='segment-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        user_id = "tester"
        company_code = "Sv"

        if "segment-ids" in request.query_params:
            segment_ids = request.query_params.getlist("segment-ids")
        else:
            segment_ids = [str(request.query_params["segment-id"])]
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_segment_executor.get_segment_target_columns,
            service_db_info=service_db_info,
            company_code=company_code,
            segment_ids=segment_ids,
        )

        segment_target_columns_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(segment_target_columns_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


# @app.post("/ml/model/nice-auto-ml")
#/serving/model/export/nice-auto-ml
@app.post("/serving/model/export/nice-auto-ml")
@web_utils.web_err_handler
@web_utils.auth_handler
async def ml_export_nice_auto_ml_mdl(request: Request, body: ExportNiceAutoMLMdl):
    """
    [2026-06-25 dyk] automl mdl 파일 export, 현재 사용 확인 필요.
    """
    app_state = request.app.state
    app_config = app_state.config
    try:
        json_obj = await request.json()

        user_id = "tester"  # request["user"]["id"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        company_code = "Sv"  # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        json_obj["UserId"] = user_id
        json_obj["CompanyCode"] = company_code

        service_db_info = db_utils.get_service_db_info_from_app(app_config)
        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        exec_func = functools.partial(
            serving_export_executor.ml_export_nice_auto_ml_mdl,
            company_db_info=company_db_info,
            file_server_host=app_config["FILE_SERVER_HOST"],
            file_server_port=app_config["FILE_SERVER_PORT"],
            h2o_file_server_host=app_config["H2O_FILE_SERVER_HOST"],
            h2o_file_server_port=app_config["H2O_FILE_SERVER_PORT"],
            h2o_host=app_config["H2O_SERVER_HOST"],
            h2o_port=_get_next_h2o_port(app_config),
            h2o_older_version_port=app_config["H2O_OLDER_VERSION_PORT"],
            root_dir=app_config["ROOT_DIR"],
            json_obj=json_obj,
        )
        model_bytes = await asyncio.to_thread(exec_func)

        return await web_utils.stream_response(model_bytes, request)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


## 태스크 관련 API
#/serving/task
@app.get("/serving/task")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_task(request: Request, product_id: int = Query(alias='product-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # auth_key = request.query_params["auth-key"]
        product_id = int(request.query_params["product-id"])

        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_task_executor.get_task,
            service_db_info=service_db_info,
            product_id=product_id,
            company_code=company_code,
            user_id=user_id
        )

        task_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(task_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/task-meta
@app.get("/serving/task-meta")
@web_utils.web_err_handler
@web_utils.auth_handler
async def serving_get_task(request: Request, task_id: int = Query(alias='task-id')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        # auth_key = request.query_params["auth-key"]
        task_id = int(request.query_params["task-id"])

        # TODO request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        user_id = "tester"
        company_code = "Sv"

        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        exec_func = functools.partial(
            serving_task_executor.get_task_meta,
            service_db_info=service_db_info,
            task_id=task_id,
            company_code=company_code
        )

        task_list_json = await asyncio.to_thread(exec_func)

        # return #{'APPLY_NEW_MAPPING': 0, 'CALIB_BASE_HISTORY': None, 'END_DATE': datetime.date(2028, 6, 9), 'FLOW_...
        return web_utils.json_response(task_list_json)

    except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


#/serving/task/sendreport/segment-list
@app.get("/serving/task/sendreport/segment-list")
@web_utils.web_err_handler
@web_utils.auth_handler
async def get_flow_list_for_report(request: Request, product_ids: int = Query(alias='id'),
                                     task_yn: int = Query(alias='task-yn')):
    app_state = request.app.state
    app_config = app_state.config
    try:
        service_db_info = db_utils.get_service_db_info_from_app(app_config)

        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        # request["user"]["company"] auth_handler 에서 keycloak 통해서 주입 해줘야 함
        # json_obj["UserId"] = "tester"
        # json_obj["CompanyCode"] = "Sv"
        user_id = "tester"
        company_code = "Sv"

        company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
        company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

        # auth_key = request.query_params["auth-key"]
        product_ids = request.query_params["id"]
        task_yn = request.query_params["task-yn"]

        exec_func = functools.partial(
            serving_task_executor.get_flow_list_for_report,
            # service_db_info=service_db_info,
            company_db_info=company_db_info,
            # auth_key=auth_key,
            product_ids=product_ids,
            task_yn=task_yn,
        )

        flow_list_json = await asyncio.to_thread(exec_func)

        return web_utils.json_response(flow_list_json)

       except Exception as e:
        app_config["ERROR_LOGGER"].error(traceback.format_exc())
        raise Exception(str(e))


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
                file_server_host
