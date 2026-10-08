
def get_product_list(service_db_info, user_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    select_product_query = """
        SELECT P.PRODUCT_ID,
            1 AS PRODUCT_TYPE,
            P.CURRENT_PROD_HIST_ID AS PRODUCT_HISTORY_ID,
            PRODUCT_NAME,
            PRODUCT_DETAIL AS PRODUCT_SHORT_DESC,
            USER_ID AS OWNER_ID,
            COUNT(PSH.PRODUCT_ID) AS SEGMENT_COUNT,
            ENROLLED_DATETIME,
            LAST_MODIFIED_DATETIME
        FROM TB_SV_PRODUCT P LEFT JOIN TB_SV_PRODUCT_SEGMENT_HISTORY PSH
        ON P.PRODUCT_ID = PSH.PRODUCT_ID
        AND P.CURRENT_PROD_HIST_ID = PSH.PRODUCT_HISTORY_ID
        WHERE USER_ID = %s
        GROUP BY P.PRODUCT_ID, P.CURRENT_PROD_HIST_ID
        ORDER BY LAST_MODIFIED_DATETIME DESC
    """

    product_list_json = db_utils.execute_select_query(
        company_db_info, select_product_query, (user_id,)
    )

    return product_list_json
def get_product(service_db_info, company_code, user_id):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    # TODO - 검토
    select_product_query = """
        SELECT P.PRODUCT_ID, P.PRODUCT_NAME, P.PRODUCT_DETAIL AS PRODUCT_SHORT_DESC,
            P.CURRENT_PROD_HIST_ID, P.USER_ID AS OWNER_ID, P.ENROLLED_DATETIME,
            P.LAST_MODIFIED_DATETIME, P.PRODUCT_MEMO AS PRODUCT_LONG_DESC,
            (SELECT COUNT(*) FROM TB_SV_SEGMENT S WHERE S.PRODUCT_ID = P.PRODUCT_ID) AS SEGMENT_COUNT
        FROM TB_SV_PRODUCT P
    """

    product_json = db_utils.execute_select_query(
        company_db_info, select_product_query, ()
    )

    if not product_json:
        product_json = []

    return product_json
def add_product(company_db_info, file_server, h2o_server, json_obj, root_dir):
    user_id = json_obj["UserId"]
    product_name = json_obj["ProductName"]
    product_short_desc = json_obj["ProductShortDesc"]
    product_long_desc = json_obj["ProductLongDesc"]
    segment_val_name = json_obj["SegmentColumn"]
    exclusion_val_nm = json_obj["ExclusionColumn"]
    segments = json_obj["Segments"]

    # 1. 상품 명 중복 검사
    select_product_cnt_query = """
        SELECT COUNT(*) AS CNT FROM TB_SV_PRODUCT WHERE PRODUCT_NAME = %s
    """
    select_product_cnt_param = (product_name,)
    product_name_cnt = db_utils.execute_select_query(
        company_db_info,
        select_product_cnt_query,
        select_product_cnt_param
    )

    if product_name_cnt[0]["CNT"] > 0:
        raise Exception("There is a product which has the same name you wrote down!")

    # 2. 상품 기본 정보 추가 -> PRODUCT ID 생성
    add_product_query = """
        INSERT INTO TB_SV_PRODUCT(PRODUCT_NAME, PRODUCT_DETAIL, PRODUCT_MEMO, USER_ID)
        VALUES(%s, %s, %s, %s);
    """

    add_product_param = (product_name, product_short_desc, product_long_desc, user_id)
    select_new_product_id = """SELECT LAST_INSERT_ID() AS PRODUCT_ID;"""
    product_id_json = db_utils.execute_modify_query(
        company_db_info,
        add_product_query,
        add_product_param,
        select_new_product_id,
    )

    if len(product_id_json) == 0:
        raise Exception("Product not added successfully.")
    product_id = int(product_id_json[0]["PRODUCT_ID"])

    # 3. 세그먼트 추가 -> SEGMENT_ID, SEGMENT_HISTORY_ID 생성
    add_segment_result_list = []
    for seg_json_obj in segments:
        seg_json_obj["ProductId"] = product_id
        result = add_segment(company_db_info, file_server, h2o_server, seg_json_obj, root_dir)
        add_segment_result_list.append(result)

    # 4. 상품 히스토리 정보 추가 -> PRODUCT_HISTORY_ID 생성 -> CURRENT_HIST_ID 갱신 -> 상품:세그먼트 n개 매핑
    add_product_history_query = """
        INSERT INTO TB_SV_PRODUCT_HISTORY(PRODUCT_ID, HISTORY_NAME, HISTORY_DETAIL, HISTORY_TYPE, SEGMENT_VAL_NM, EXCLUSION_VAL_NM)
        VALUES(%s, %s, %s, %s, %s, %s);
    """

    add_product_history_param = (product_id, "ADD PRODUCT", "상품 최초 생성", 'CREATE', segment_val_name, exclusion_val_nm)
    set_product_history_id_query = """SET @NEW_PROD_HIST_ID = LAST_INSERT_ID();"""
    set_product_history_id_param = ()
    update_current_history_id_query = """
        UPDATE TB_SV_PRODUCT
        SET CURRENT_PROD_HIST_ID = @NEW_PROD_HIST_ID
        WHERE PRODUCT_ID = %s;
    """

    update_current_history_id_param = (product_id,)
    add_product_segment_query = """
        INSERT INTO TB_SV_PRODUCT_SEGMENT_HISTORY(PRODUCT_ID, PRODUCT_HISTORY_ID, SEGMENT_ID, SEGMENT_HISTORY_ID)
        VALUES(%s, @NEW_PROD_HIST_ID, %s, %s)
    """

    add_product_history_query_list = [add_product_history_query, set_product_history_id_query, update_current_history_id_query]
    add_product_history_param_list = [add_product_history_param, set_product_history_id_param, update_current_history_id_param]
    for seg_result in add_segment_result_list:
        add_product_history_query_list.append(add_product_segment_query)
        add_product_history_param_list.append((product_id, seg_result["SEGMENT_ID"], seg_result["SEGMENT_HISTORY_ID"]))
    select_new_product_history_id = """SELECT @NEW_PROD_HIST_ID AS HISTORY_ID;"""
    product_history_id_json = db_utils.execute_modify_query(
        company_db_info,
        add_product_history_query_list,
        add_product_history_param_list,
        select_new_product_history_id
    )

    if len(product_history_id_json) == 0:
        raise Exception("Product not added successfully.")
    product_history_id = int(product_history_id_json[0]["HISTORY_ID"])

    return {'PRODUCT_ID': product_id, 'PRODUCT_HISTORY_ID': product_history_id}
def get_product_feature(service_db_info, product_id, user_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    feature_list_json = list()

    select_current_feature_id_query = """
        SELECT MAX(PRODUCT_VAR_ID) AS CURRENT_PRODUCT_VAR_ID
        FROM TB_SV_PRODUCT_VAR_MNG
        WHERE PRODUCT_ID = %s
    """

    current_feature_id_json = db_utils.execute_select_query(
        db_info=company_db_info,
        query=select_current_feature_id_query,
        param=(product_id,),
    )

    current_feature_id = current_feature_id_json[0]["CURRENT_PRODUCT_VAR_ID"]

    if current_feature_id is None:
        return feature_list_json

    select_feature_list_query = """
        SELECT PVI.PRODUCT_VAR_ID, PVI.VAR_NM, PVI.VAR_DESC, PVI.VAR_FORM, PVI.IS_PERF_COL, CC.VALUE AS VAR_FORM_NAME
        FROM TB_SV_PRODUCT_VAR_INFO PVI
        LEFT JOIN TB_COM_CODE CC
        ON PVI.VAR_FORM = CC.KEY
        WHERE PVI.PRODUCT_VAR_ID = %s
    """

    feature_list_json = db_utils.execute_select_query(
        db_info=company_db_info,
        query=select_feature_list_query,
        param=(current_feature_id,),
    )

    return feature_list_json
def get_product_feature_group_list(service_db_info, company_code, product_id):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    select_feature_grp_list_query = """
        SELECT PVGM.PRODUCT_VAR_GRP_ID AS VAR_GROUP_ID, PVGM.PRODUCT_VAR_GRP_NAME AS VAR_GROUP_NAME
        FROM TB_SV_PRODUCT_VAR_MNG PVM
        LEFT JOIN TB_SV_PRODUCT_VAR_GRP_MNG PVGM
            ON PVM.PRODUCT_VAR_ID = PVGM.PRODUCT_VAR_ID
        WHERE PVM.PRODUCT_ID = %s
        AND PVM.PRODUCT_VAR_ID = (
            SELECT MAX(PRODUCT_VAR_ID) FROM TB_SV_PRODUCT_VAR_MNG WHERE PRODUCT_ID = %s
        )
        AND PVGM.PRODUCT_VAR_GRP_ID IS NOT NULL
    """

    feature_grp_list_json = db_utils.execute_select_query(
        db_info=company_db_info,
        query=select_feature_grp_list_query,
        param=(product_id, product_id),
    )

    return feature_grp_list_json
def get_product_feature_group_var(service_db_info, feature_grp_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    select_feature_grp_query = """
        SELECT VAR_NM, VAR_DESC, VAR_DOMAIN, VAR_FORM, IS_PERF_COL, MONOTONICITY
        FROM TB_SV_PRODUCT_VAR_GRP_INFO
        WHERE PRODUCT_VAR_GRP_ID = %s
        ORDER BY VAR_NM
    """

    feature_grp_json = db_utils.execute_select_query(
        db_info=company_db_info,
        query=select_feature_grp_query,
        param=(feature_grp_id,),
    )

    return feature_grp_json
def add_segment(company_db_info, file_server, h2o_server, json_obj, root_dir):
    user_id = json_obj["UserId"]
    product_id = json_obj["ProductId"]
    segment_name = json_obj["SegmentName"]
    segment_detail = json_obj["SegmentDetail"]
    segment_var_value = json_obj["SegmentValue"]
    exclusion_val_value = json_obj["ExclusionValue"]

    pdo = json_obj["Pdo"]
    anchor = json_obj["Anchor"]

    has_grade = json_obj["HasGrade"]
    grade = json_obj["Grade"]
    has_calibration = json_obj["HasCalibration"]
    calibration = json_obj["Calibration"]

    models = json_obj["Models"]

    # 1. 세그먼트 기본 정보 추가 -> SEGMENT_ID 생성
    add_segment_query = """
        INSERT INTO TB_SV_SEGMENT(PRODUCT_ID, SEGMENT_NAME, SEGMENT_DETAIL, USER_ID)
        VALUES(%s, %s, %s, %s)
    """

    add_segment_param = (product_id, segment_name, segment_detail, user_id)
    select_new_segment_id = """SELECT LAST_INSERT_ID() AS SEGMENT_ID;"""
    segment_id_json = db_utils.execute_modify_query(
        company_db_info,
        add_segment_query,
        add_segment_param,
        select_new_segment_id,
    )

    if len(segment_id_json) == 0:
        raise Exception("Segment not added successfully.")
    segment_id = int(segment_id_json[0]["SEGMENT_ID"])

    # 2. 등급 정보 추가 -> GRADE_ID 생성
    grade_id = None
    if has_grade:
        add_grade_id_query = """
            INSERT INTO TB_SV_SEGMENT_GRADE_MNG(SEGMENT_ID, GRADE_NAME, GRADE_DETAIL)
            VALUES(%s, %s, %s);
        """

        add_grade_id_param = (segment_id, "ADD_GRADE", "ADD_GRADE")
        set_grade_id_query = """SET @NEW_GRADE_ID = LAST_INSERT_ID();"""
        set_grade_id_param = ()

        add_grade_query_list = [add_grade_id_query, set_grade_id_query]
        add_grade_param_list = [add_grade_id_param, set_grade_id_param]
        add_grade_info_query = """
            INSERT INTO TB_SV_SEGMENT_GRADE_INFO(GRADE_ID, GRADE, LOWER, UPPER)
            VALUES (@NEW_GRADE_ID, %s, %s, %s);
        """

        for row in grade:
            add_grade_query_list.append(add_grade_info_query)
            add_grade_param_list.append((row["GRADE"], row["MIN"], row["MAX"]))

        select_new_id_query = """SELECT @NEW_GRADE_ID AS GRADE_ID"""
        new_id_json = db_utils.execute_modify_query(
            company_db_info,
            add_grade_query_list,
            add_grade_param_list,
            select_new_id_query,
        )
        grade_id = int(new_id_json[0]["GRADE_ID"])

    # 3. Calibration 정보 추가 -> MAPPING_ID 생성
    mapping_id = None
    if has_calibration:
        add_mapping_id_query = """
            INSERT INTO TB_SV_SEGMENT_CALIBRATION_MNG(SEGMENT_ID, MAPPING_NAME, MAPPING_DETAIL)
            VALUES(%s, %s, %s);
        """

        add_mapping_id_param = (segment_id, "ADD_CALIBRATION", "ADD_CALIBRATION")
        set_mapping_id_query = """SET @NEW_MAPPING_ID = LAST_INSERT_ID();"""
        set_mapping_id_param = ()

        add_mapping_query_list = [add_mapping_id_query, set_mapping_id_query]
        add_mapping_param_list = [add_mapping_id_param, set_mapping_id_param]
        add_mapping_info_query = """
            INSERT INTO TB_SV_SEGMENT_CALIBRATION_INFO(MAPPING_ID, MIN_CLOSED, MAX_OPEN, MIN_CLOSED_MAP, MAX_OPEN_MAP)
            VALUES (@NEW_MAPPING_ID, %s, %s, %s, %s);
        """

        for row in calibration:
            max_open = int(row["SCORE"]) + 1
            min_closed = np.iinfo(np.int16).min if max_open == 1 else max_open - 1
            if max_open >= 1000:
                max_open = np.iinfo(np.int16).max

            min_closed_map = max(int(row["MAPPED_SCORE"]), 0)
            max_open_map = min_closed_map + 1

            add_mapping_query_list.append(add_mapping_info_query)
            add_mapping_param_list.append((min_closed, max_open, min_closed_map, max_open_map))

        select_new_id_query = """SELECT @NEW_MAPPING_ID AS MAPPING_ID"""
        new_id_json = db_utils.execute_modify_query(
            company_db_info,
            add_mapping_query_list,
            add_mapping_param_list,
            select_new_id_query,
        )
        mapping_id = int(new_id_json[0]["MAPPING_ID"])

    # 4. 모형 추가 -> MODEL_ID, MODEL_HISTORY_ID 생성
    h2o_server["PORT"] = serving_utils._get_next_h2o_port(h2o_server["HOST"], h2o_server["PORTS"])
    add_model_result_list = []
    for model_json_obj in models:
        model_json_obj["SegmentId"] = segment_id
        result = add_model(company_db_info, file_server, h2o_server, model_json_obj, root_dir)
        add_model_result_list.append(result)

    # 5. 세그먼트 히스토리 정보 추가 -> SEGMENT HISTORY ID 생성 -> CURRENT_HIST_ID 갱신 -> 세그먼트:모형 n개 매핑
    add_segment_history_query = """
        INSERT INTO TB_SV_SEGMENT_HISTORY(
            SEGMENT_ID, HISTORY_NAME, HISTORY_DETAIL, SEGMENT_VALUE, EXCLUSION_VALUE, PDO, ANCHOR, MAPPING_ID, GRADE_ID)
        VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s);
    """

    add_segment_history_param = (segment_id, "ADD_SEG", "ADD_SEG", segment_var_value, exclusion_val_value, pdo, anchor, mapping_id, grade_id)
    set_segment_history_id_query = """SET @NEW_SEG_HIST_ID = LAST_INSERT_ID();"""
    set_segment_history_id_param = ()
    update_current_history_id_query = """
        UPDATE TB_SV_SEGMENT
        SET CURRENT_SEG_HIST_ID = @NEW_SEG_HIST_ID
        WHERE SEGMENT_ID = %s;
    """

    update_current_history_id_param = (segment_id,)
    add_segment_history_query_list = [add_segment_history_query, set_segment_history_id_query, update_current_history_id_query]
    add_segment_history_param_list = [add_segment_history_param, set_segment_history_id_param, update_current_history_id_param]
    add_segment_model_query = """
        INSERT INTO TB_SV_SEGMENT_MODEL_HISTORY(SEGMENT_ID, SEGMENT_HISTORY_ID, MODEL_ID, MODEL_HISTORY_ID)
        VALUES (%s, @NEW_SEG_HIST_ID, %s, %s)
    """

    for model_result in add_model_result_list:
        add_segment_history_query_list.append(add_segment_model_query)
        add_segment_history_param_list.append((segment_id, model_result["MODEL_ID"], model_result["MODEL_HISTORY_ID"]))
    select_new_segment_history_id = """SELECT @NEW_SEG_HIST_ID AS HISTORY_ID;"""
    segment_history_id_json = db_utils.execute_modify_query(
        company_db_info,
        add_segment_history_query_list,
        add_segment_history_param_list,
        select_new_segment_history_id,
    )

    if len(segment_history_id_json) == 0:
        raise Exception("Segment not added successfully.")
    segment_history_id = int(segment_history_id_json[0]["HISTORY_ID"])

    return {"SEGMENT_ID": segment_id, "SEGMENT_HISTORY_ID": segment_history_id}
def add_model(company_db_info, file_server, h2o_server, json_obj, root_dir):
    user_id = json_obj["UserId"]
    company_code = json_obj["CompanyCode"]

    segment_id = json_obj["SegmentId"]
    model_name = json_obj["ModelName"]
    model_detail = json_obj["ModelDetail"] if "ModelDetail" in json_obj else ""
    model_type = json_obj["ModelType"]
    temp_model_file = json_obj["TempFileName"]
    weight = json_obj["Weight"]

    reverse_prob = json_obj["Reverse"] if "Reverse" in json_obj else True

    # ZIP 파일이 아니면 PMML 로 판단. 다른 형태의 모형이 추가될 경우 변경 필요.
    model_format = "MDL" if zipfile.is_zipfile(temp_model_file) else "PMML"

    # 1. 모형 파일 업로드
    model_file_name, layout_file_name, model_meta_file_name = serving_utils.upload_mdl_file(
        root_dir, file_server, h2o_server, company_code, temp_model_file, model_type
    ) if model_format == "MDL" else serving_utils.upload_pmml_file(
        root_dir, file_server, h2o_server, company_code, temp_model_file, model_type
    )

    # 2. 모형 기본 정보 추가 -> MODEL ID 생성
    add_model_query = """
        INSERT INTO TB_SV_MODEL(SEGMENT_ID, MODEL_NAME, MODEL_DETAIL, MODEL_TYPE, USER_ID, MODEL_FORMAT)
        VALUES(%s, %s, %s, %s, %s, %s)
    """
    add_model_param = (segment_id, model_name, model_detail, model_type, user_id, model_format)
    set_model_id_query = """SET @NEW_MODEL_ID = LAST_INSERT_ID();"""
    set_model_id_param = ()

    # 3. 모형 히스토리 정보 추가 -> MODEL HISTORY ID 생성
    add_model_history_query = """
        INSERT INTO TB_SV_MODEL_HISTORY(MODEL_ID, HISTORY_NAME, HISTORY_DETAIL, MODEL_FILE_NAME, LAYOUT_FILE_NAME, META_FILE_NAME, WEIGHT, REVERSE_PROB)
        VALUES(@NEW_MODEL_ID, %s, %s, %s, %s, %s, %s, %s);
    """
    add_model_history_param = ("ADD_MODEL", "ADD_MODEL", model_file_name, layout_file_name, model_meta_file_name, weight, reverse_prob)
    set_model_hist_id_query = """SET @NEW_MODEL_HISTORY_ID = LAST_INSERT_ID();"""
    set_model_hist_id_param = ()

    # 4. CURRENT_HIST_ID 갱신
    update_current_history_id_query = """
        UPDATE TB_SV_MODEL
        SET CURRENT_MODEL_HIST_ID = @NEW_MODEL_HISTORY_ID
        WHERE MODEL_ID = @NEW_MODEL_ID;
    """
    update_current_history_id_param = ()
    select_new_id_query = """SELECT @NEW_MODEL_ID AS MODEL_ID, @NEW_MODEL_HISTORY_ID AS HISTORY_ID"""
    new_id_json = db_utils.execute_modify_query(
        company_db_info,
        query=[add_model_query, set_model_id_query, add_model_history_query, set_model_hist_id_query, update_current_history_id_query, select_new_id_query],
        param=[add_model_param, set_model_id_param, add_model_history_param, set_model_hist_id_param, update_current_history_id_param],
        select_new_id_query,
    )

    model_id = int(new_id_json[0]["MODEL_ID"])
    model_history_id = int(new_id_json[0]["HISTORY_ID"])

    return {"MODEL_ID": model_id, "MODEL_HISTORY_ID": model_history_id}

def modify_models_compare(company_db_info, segment_id, segment_history_id, models_json):
    """
    Model 변경 여부 확인
        Model Name, Model Detail 바뀐 경우 TV_SV_MODEL 테이블 update
        Weight, Reverse_Prob, Model 바뀐 경우 변경 여부 True

    Return
        변경 여부
        변경 되지 않은 Model ID 리스트
    """
    # user_id = json_obj["UserId"]
    # company_code = json_obj["CompanyCode"]

    # query from get_product_history_details()
    select_model_query = """
        SELECT M.MODEL_ID,
               M.MODEL_NAME,
               M.MODEL_DETAIL,
               SMH.MODEL_HISTORY_ID,
               M.MODEL_TYPE,
               MH.MODEL_FILE_NAME,
               MH.WEIGHT,
               MH.REVERSE_PROB
        FROM TB_SV_MODEL M, TB_SV_SEGMENT_MODEL_HISTORY SMH, TB_SV_MODEL_HISTORY MH, TB_SV_SEGMENT S
        WHERE SMH.SEGMENT_ID = %s
          AND SMH.SEGMENT_ID = S.SEGMENT_ID
          AND SMH.SEGMENT_HISTORY_ID = S.CURRENT_SEG_HIST_ID
          AND SMH.MODEL_ID = M.MODEL_ID
          AND SMH.MODEL_HISTORY_ID = MH.HISTORY_ID
    """

    select_model_json = db_utils.execute_select_query(
        company_db_info, select_model_query, param=(segment_id,)
    )

    # 모델 개수가 바뀜 / weight 가 다 바뀌어야 하므로 유지 모델 없음
    if len(select_model_json) != len(models_json):
        # return [m["MODEL_ID"] for m in select_model_json]
        return True, []

    same_model_id_list = []
    hist_change = False  # weight, model file
    for cur_model in select_model_json:
        new_model = next((m for m in models_json if m["ModelId"] == cur_model["MODEL_ID"]), None)
        if new_model is None:
            hist_change = True

        # name, detail 변경은 history 변경 없이 바로 처리
        if (cur_model["MODEL_NAME"] != new_model["ModelName"]
            or cur_model["MODEL_DETAIL"] != new_model["ModelDetail"]):
            update_model_info_query = """
                UPDATE TB_SV_MODEL
                SET MODEL_NAME = %s, MODEL_DETAIL = %s
                WHERE MODEL_ID = %s
            """
            update_model_info_params = (new_model["ModelName"], new_model["ModelDetail"], new_model["ModelId"])
            update_model_json = db_utils.execute_modify_query(
                company_db_info,
                update_model_info_query,
                update_model_info_params,
            )

        if ((cur_model["WEIGHT"] != new_model["Weight"])
            or (cur_model["REVERSE_PROB"] != new_model["Reverse"])
            or (new_model["TempFileName"] != '')):
            hist_change = True
        else:
            same_model_id_list.append(cur_model["MODEL_ID"])  # 미변경 모델

    return hist_change, same_model_id_list


def modify_models(company_db_info, json_obj, file_server, h2o_server, root_dir):
    """
    Model 변경
        modify_model_check() 후 수행
    model_json : 해당 segment의 모든 model 목록
        ex : [{'CompanyCode': 'Sv', 'UserId': 'tester', 'ModelId': 16,
              'ModelName': 'm2', 'ModelDetail': 'm2 dt', 'Weight': 0.7, 'Reverse': true, 'ModelType': 'LIGHTGBM'},
             {'CompanyCode': 'Sv', 'UserId': 'tester', 'ModelId': 'dba69ea8-a272-5959-a810-8b2451766b2c',
              'ModelName': 'm3', 'ModelDetail': 'm3 dt', 'Weight': 0.3, 'Reverse': false, 'ModelFile': {}, 'ModelType': 'GRADIENTBOOSTING'}]
    id_list : 미변경 모델의 MODEL_ID 리스트 / modify_model_compare() 두번째 출력값

    Return : 처리된 모델 수
    """
    # user_id = json_obj["UserId"]
    # company_code = json_obj["CompanyCode"]
    segment_id = json_obj["SegmentId"]
    segment_history_id = json_obj["SegmentHistoryId"]
    new_segment_history_id = json_obj["NewSegmentHistoryId"]
    models_json = json_obj["Models"]
    same_model_id_list = json_obj["UnmodifiedList"]

    cnt = 0
    try:
        for model in models_json:
            modify_models_queries = []
            modify_models_params = []

            # TB_SV_SEGMENT_MODEL_HISTORY
            if(model["ModelId"] in same_model_id_list):
                ''' unmodified model '''
                add_segment_model_history_query = """
                    INSERT INTO TB_SV_SEGMENT_MODEL_HISTORY
                    SELECT SEGMENT_ID, %s, MODEL_ID, MODEL_HISTORY_ID
                    FROM TB_SV_SEGMENT_MODEL_HISTORY
                    WHERE SEGMENT_ID = %s
                      AND SEGMENT_HISTORY_ID = %s
                      AND MODEL_ID = %s
                """

                add_segment_model_history_param = (new_segment_history_id, segment_id, segment_history_id, model["ModelId"])
                modify_models_queries.append(add_segment_model_history_query)
                modify_models_params.append(add_segment_model_history_param)
            else:
                ''' modified model '''
                ''' Model File 은 변경 없이 신규 입력 가능하므로 (weight|reverse),file 동시에 변경 케이스 없음 '''
                if (("TempFileName" in model) and (model["TempFileName"] != '')): # file exist => new model
                    model["SegmentId"] = segment_id
                    result = add_model(company_db_info, file_server, h2o_server, model, root_dir)
                    add_segment_model_history_query = """
                        INSERT INTO TB_SV_SEGMENT_MODEL_HISTORY(SEGMENT_ID, SEGMENT_HISTORY_ID, MODEL_ID, MODEL_HISTORY_ID)
                        VALUES (%s, %s, %s, %s)
                    """

                    add_segment_model_history_param = (segment_id, new_segment_history_id,
                                                        result["MODEL_ID"], result["MODEL_HISTORY_ID"])

                    set_model_hist_id_query = """SET @NEW_MODEL_HISTORY_ID = LAST_INSERT_ID();"""
                    set_model_hist_id_param = ()

                    modify_models_queries.append(add_segment_model_history_query)
                    modify_models_params.append(add_segment_model_history_param)
                    modify_models_queries.append(set_model_hist_id_query)
                    modify_models_params.append(set_model_hist_id_param)

                else: # weight or reverse
                    add_model_history_query = """
                        INSERT INTO TB_SV_MODEL_HISTORY(MODEL_ID, HISTORY_NAME, HISTORY_DETAIL,
                                                       MODEL_FILE_NAME, LAYOUT_FILE_NAME, WEIGHT, REVERSE_PROB)
                        SELECT S.MODEL_ID, %s, %s, S.MODEL_FILE_NAME, S.LAYOUT_FILE_NAME, %s, %s
                        FROM TB_SV_MODEL_HISTORY S, TB_SV_MODEL M
                        WHERE S.MODEL_ID = M.MODEL_ID
                          AND S.HISTORY_ID = M.CURRENT_MODEL_HIST_ID
                          AND S.MODEL_ID = %s
                    """

                    add_model_history_param = ("ADD_MODEL", "ADD_MODEL", model["Weight"],
                                                model["Reverse"] if "Reverse" in model else True,
                                                model["ModelId"])

                    set_model_hist_id_query = """SET @NEW_MODEL_HISTORY_ID = LAST_INSERT_ID();"""
                    set_model_hist_id_param = ()

                    add_segment_model_history_query = """
                        INSERT INTO TB_SV_SEGMENT_MODEL_HISTORY(SEGMENT_ID, SEGMENT_HISTORY_ID, MODEL_ID, MODEL_HISTORY_ID)
                        VALUES (%s, %s, %s, @NEW_MODEL_HISTORY_ID)
                    """

                    add_segment_model_history_param = (segment_id, new_segment_history_id, model["ModelId"])

                    update_model_query = """
                        UPDATE TB_SV_MODEL
                        SET CURRENT_MODEL_HIST_ID = @NEW_MODEL_HISTORY_ID
                        WHERE MODEL_ID = %s
                    """

                    update_model_param = (model["ModelId"],)

                    modify_models_queries.append(add_model_history_query)
                    modify_models_params.append(add_model_history_param)
                    modify_models_queries.append(set_model_hist_id_query)
                    modify_models_params.append(set_model_hist_id_param)
                    modify_models_queries.append(add_segment_model_history_query)
                    modify_models_params.append(add_segment_model_history_param)
                    modify_models_queries.append(update_model_query)
                    modify_models_params.append(update_model_param)

            select_segment_model_history_query = """SELECT @NEW_MODEL_HISTORY_ID AS SMH_ID;"""

            new_smh_id_json = db_utils.execute_modify_query(
                company_db_info,
                modify_models_queries,
                modify_models_params,
                select_segment_model_history_query
            )

            if len(new_smh_id_json) == 0:
                raise Exception("Modified model history not saved successfully.")
            cnt = cnt + 1
    except:
        raise Exception("Model Modification Failed.")

    return cnt

def get_model_history_list(company_db_info, model_id, filter_flag : int =0):
    result_history_json = []

    if filter_flag == 0 or filter_flag == 1:
        select_model_history_query = """
            SELECT HISTORY_ID, HISTORY_NAME, HISTORY_DETAIL,
                   'False' AS IS_SEGMENT_HISTORY_STR, FALSE AS IS_SEGMENT_HISTORY,
                   MODEL_ID, -1 AS SEGMENT_ID
            FROM TB_SV_MODEL_HISTORY
            WHERE MODEL_ID = %s
            ORDER BY HISTORY_ID
        """

        model_history_list_json = db_utils.execute_select_query(
            company_db_info, select_model_history_query, param=(model_id,)
        )
        result_history_json += model_history_list_json

    if filter_flag == 0 or filter_flag == 2:
        select_flow_model_history_query = """
            SELECT SH.HISTORY_ID, SH.HISTORY_NAME, SH.HISTORY_DETAIL, SMH.MODEL_ID,
                   CONCAT('True(', S.SEGMENT_NAME, ')') AS IS_FLOW_HISTORY_STR,
                   TRUE                                AS IS_FLOW_HISTORY,
                   S.SEGMENT_ID
            FROM TB_SV_SEGMENT_MODEL_HISTORY SMH
            JOIN TB_SV_SEGMENT S
              ON SMH.SEGMENT_ID = S.SEGMENT_ID AND SMH.SEGMENT_HISTORY_ID = S.CURRENT_SEG_HIST_ID
            JOIN TB_SV_SEGMENT_PREDICT_MODEL_PERF_HISTORY SPMPH
              ON SMH.MODEL_ID = SPMPH.MODEL_ID AND SMH.SEGMENT_ID = SPMPH.SEGMENT_ID
            JOIN TB_SV_SEGMENT_HISTORY SH
              ON SPMPH.HISTORY_ID = SH.HISTORY_ID
            WHERE SMH.MODEL_ID = %s;
        """

        segment_model_history_list_json = db_utils.execute_select_query(
            company_db_info, select_flow_model_history_query, param=(model_id,)
        )
        result_history_json += segment_model_history_list_json

    return result_history_json


# [2019-08-06] pjh - get current model history id

# [2019-08-06] pjh - get current model history id
def get_current_model_history_id(company_db_info, model_id):
    select_model_history_id_query = """
        SELECT
            CASE WHEN CURRENT_MODEL_HIST_ID IS NULL THEN -1
            ELSE CURRENT_MODEL_HIST_ID
            END AS CURRENT_MODEL_HIST_ID
        FROM
            TB_SV_MODEL
        WHERE
            MODEL_ID = %s
    """

    model_history_id_json = db_utils.execute_select_query(
        company_db_info, select_model_history_id_query, param=(model_id,)
    )
    model_history_id = model_history_id_json[0]["MODEL_HISTORY_ID"]
    return model_history_id


def add_product_feature(company_db_info, json_obj):
    product_id = json_obj["ProductId"]
    features_list = json_obj["Features"]

    product_var_name = "ADD PRODUCT FEATURES"
    product_var_detail = "후보 항목 저장"

    try:
        # PRODUCT_ID와 매핑되는 PRODUCT_VAR_ID 가져옴
        select_var_id_query = """
            SELECT PRODUCT_VAR_ID
            FROM TB_SV_PRODUCT_VAR_MNG
            WHERE PRODUCT_ID = %s
            ORDER BY PRODUCT_VAR_ID DESC;
        """

        product_var_id_json = db_utils.execute_select_query(db_info=company_db_info, query=select_var_id_query,
                                                             param=(product_id,))

        if len(product_var_id_json) <= 0:
            add_product_var_id_query = """
                INSERT INTO TB_SV_PRODUCT_VAR_MNG(PRODUCT_ID, PRODUCT_VAR_NAME, PRODUCT_VAR_DETAIL)
                VALUES (%s, %s, %s);
            """

            add_product_var_id_param = (
                product_id,
                product_var_name,
                product_var_detail,
            )

            set_product_var_id_query = """SET @NEW_PROD_VAR_ID = LAST_INSERT_ID();"""

            select_new_product_var_id = """SELECT @NEW_PROD_VAR_ID AS PRODUCT_VAR_ID;"""

            product_var_id_json = db_utils.execute_modify_query(
                company_db_info,
                query=[add_product_var_id_query, set_product_var_id_query],
                param=[add_product_var_id_param, ()],
                select_new_product_var_id
            )

            if len(product_var_id_json) == 0:
                raise Exception("Features not saved successfully.")

        product_var_id = product_var_id_json[0]["PRODUCT_VAR_ID"]
        add_product_var_queries = []
        add_product_var_params = []

        for feature in features_list:
            insert_feature_query = """
                INSERT INTO TB_SV_PRODUCT_VAR_INFO(PRODUCT_VAR_ID, VAR_NM, VAR_DESC, VAR_FORM, IS_PERF_COL, FLAG)
                VALUES(%s, %s, %s, %s, %s, 1);
            """

            insert_feature_param = (
                product_var_id,
                feature["VAR_NM"],
                feature["VAR_DESC"],
                feature["VAR_FORM"],
                feature["IS_PERF_COL"],
            )

            add_product_var_queries.append(insert_feature_query)
            add_product_var_params.append(insert_feature_param)

        db_utils.execute_modify_query(
            company_db_info,
            add_product_var_queries,
            add_product_var_params,
        )

    except Exception as e:
        raise Exception("Saving Features Failed.")

    return product_var_id_json


def update_product_feature(company_db_info, json_obj):
    ###########
    product_id = json_obj["ProductId"]
    features_list = json_obj["Features"]

    try:
        # PRODUCT_ID와 매핑되는 PRODUCT_VAR_ID 가져옴
        select_var_id_query = """
            SELECT PRODUCT_VAR_ID
            FROM TB_SV_PRODUCT_VAR_MNG
            WHERE PRODUCT_ID = %s
            ORDER BY PRODUCT_VAR_ID DESC;
        """

        product_var_id_json = db_utils.execute_select_query(db_info=company_db_info, query=select_var_id_query,
                                                             param=(product_id,))

        if len(product_var_id_json) >= 0:
            product_var_id = product_var_id_json[0]["PRODUCT_VAR_ID"]
            update_product_grp_var_queries = []
            update_product_grp_var_params = []

            for feature in features_list:
                update_grp_feature_query = """
                    UPDATE TB_SV_PRODUCT_VAR_INFO
                    SET VAR_DESC=%s,
                        VAR_FORM=%s,
                        IS_PERF_COL=%s,
                        FLAG=1
                    WHERE PRODUCT_VAR_ID = %s
                      AND VAR_NM = %s;
                """

                update_grp_feature_param = (
                    feature["VAR_DESC"],
                    feature["VAR_FORM"],
                    feature["IS_PERF_COL"],
                    product_var_id,
                    feature["VAR_NM"],
                )

                update_product_grp_var_queries.append(update_grp_feature_query)
                update_product_grp_var_params.append(update_grp_feature_param)

            db_utils.execute_modify_query(
                company_db_info,
                update_product_grp_var_queries,
                update_product_grp_var_params,
            )

    except Exception as e:
        raise Exception("Saving Features Failed.")


def delete_product_feature(company_db_info, json_obj):
    product_id = json_obj["ProductId"]
    features_list = json_obj["Features"]

    try:
        # PRODUCT_ID와 매핑되는 PRODUCT_VAR_ID 가져옴
        select_var_id_query = """
            SELECT PRODUCT_VAR_ID
            FROM TB_SV_PRODUCT_VAR_MNG
            WHERE PRODUCT_ID=%s
            ORDER BY PRODUCT_VAR_ID DESC;
        """

        product_var_ids_json = db_utils.execute_select_query(db_info=company_db_info, query=select_var_id_query, param=(product_id,))
        if len(product_var_ids_json) <= 0:
            raise Exception("PRODUCT_VAR_ID doesn't exist.")

        product_var_id = product_var_ids_json[0]["PRODUCT_VAR_ID"]

        delete_product_var_queries = []
        delete_product_var_params = []

        for feature in features_list:
            delete_feature_query = """
                DELETE FROM TB_SV_PRODUCT_VAR_INFO
                WHERE PRODUCT_VAR_ID=%s
                  AND VAR_NM=%s;
            """

            delete_feature_param = (
                product_var_id,
                feature["VAR_NM"],
            )

            delete_product_var_queries.append(delete_feature_query)
            delete_product_var_params.append(delete_feature_param)

        db_utils.execute_modify_query(
            company_db_info,
            delete_product_var_queries,
            delete_product_var_params,
        )

    except Exception as e:
        raise Exception("Saving Features Failed.")


def get_feature_json(company_db_info, product_id):
    select_product_var_query = """
        SELECT VAR_NM, VAR_DESC, VAR_FORM, IS_PERF_COL
        FROM TB_SV_PRODUCT_VAR_INFO
        WHERE PRODUCT_VAR_ID = (
            SELECT MAX(PRODUCT_VAR_ID)
            FROM TB_SV_PRODUCT_VAR_MNG
            WHERE PRODUCT_ID=%s
        )
    """

    product_var_list_json = db_utils.execute_select_query(
        company_db_info, select_product_var_query, param=(product_id,)
    )

    if product_var_list_json:
        headers = list(product_var_list_json[0].keys())
    else:
        headers = []

    return product_var_list_json, headers


def get_feature_grp_json(company_db_info, product_id, product_var_grp_id):
    select_product_var_query = """
        SELECT VAR_NM, VAR_DESC, VAR_FORM, IS_PERF_COL
        FROM TB_SV_PRODUCT_VAR_GRP_INFO
        WHERE PRODUCT_VAR_GRP_ID = %s
    """

    product_var_list_json = db_utils.execute_select_query(
        company_db_info, select_product_var_query, param=(product_var_grp_id,)
    )

    if product_var_list_json:
        headers = list(product_var_list_json[0].keys())
    else:
        headers = []

    return product_var_list_json, headers

def add_product_feature_grp(service_db_info, json_obj):
    product_id = json_obj["ProductId"]
    feature_grp_name = json_obj["FeatureGroupName"]
    feature_grp_desc = json_obj["FeatureGroupDesc"]

    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, json_obj["CompanyCode"]
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    try:
        add_product_var_id_query = """
            INSERT INTO TB_SV_PRODUCT_VAR_GRP_MNG(PRODUCT_VAR_ID, PRODUCT_VAR_GRP_NAME, PRODUCT_VAR_GRP_DETAIL)
            VALUES((SELECT MAX(PRODUCT_VAR_ID) FROM TB_SV_PRODUCT_VAR_MNG WHERE PRODUCT_ID=%s), %s, %s);
        """
        add_product_var_grp_id_param = (
            product_id,
            feature_grp_name,
            feature_grp_desc,
        )

        set_product_var_grp_id_query = """SET @NEW_PROD_VAR_GRP_ID = LAST_INSERT_ID();"""
        set_product_var_grp_id_param = ()

        add_product_var_grp_queries = [add_product_var_id_query, set_product_var_grp_id_query]
        add_product_var_grp_params = [add_product_var_grp_id_param, set_product_var_grp_id_param]

        select_new_product_var_grp_id = """SELECT @NEW_PROD_VAR_GRP_ID AS VAR_GROUP_ID;"""

        product_var_grp_id_json = db_utils.execute_modify_query(
            company_db_info,
            add_product_var_grp_queries,
            add_product_var_grp_params,
            select_new_product_var_grp_id,
        )

        if len(product_var_grp_id_json) == 0:
            raise Exception("Feature Group not saved successfully.")

    except:
        raise Exception("Saving Feature Group Failed.")

    product_var_grp_id_json[0]["VAR_GROUP_NAME"] = feature_grp_name
    return product_var_grp_id_json[0]


def save_product_feature_grp(service_db_info, json_obj):
    product_id = json_obj["ProductId"]
    feature_grp_id = json_obj["FeatureGroupId"]
    features_list = json_obj["Features"]

    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, json_obj["CompanyCode"]
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    add_product_var_grp_queries = []
    add_product_var_grp_params = []

    try:
        for feature in features_list:
            insert_feature_grp_query = """
                INSERT INTO TB_SV_PRODUCT_VAR_GRP_INFO(PRODUCT_VAR_GRP_ID, VAR_NM, VAR_DESC, VAR_FORM, IS_PERF_COL, FLAG)
                VALUES(%s, %s, %s, %s, %s, 1);
            """
            insert_feature_grp_param = (
                feature_grp_id,
                feature["VAR_NM"],
                feature["VAR_DESC"],
                feature["VAR_FORM"],
                feature["IS_PERF_COL"],
            )

            add_product_var_grp_queries.append(insert_feature_grp_query)
            add_product_var_grp_params.append(insert_feature_grp_param)

        db_utils.execute_modify_query(
            company_db_info,
            add_product_var_grp_queries,
            add_product_var_grp_params,
        )

    except:
        raise Exception("Saving Feature Group Failed.")


def delete_product_feature_grp(service_db_info, json_obj):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, json_obj["CompanyCode"]
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    product_id = json_obj["ProductId"]
    feature_grp_id = json_obj["FeatureGroupId"]

    try:
        delete_feature_grp_query = """
            DELETE
            FROM TB_SV_PRODUCT_VAR_GRP_MNG
            WHERE PRODUCT_VAR_GRP_ID = %s
        """
        delete_feature_grp_query_list = [delete_feature_grp_query]
        delete_feature_grp_param_list = [(feature_grp_id,)]

        db_utils.execute_modify_query(
            company_db_info, delete_feature_grp_query_list, delete_feature_grp_param_list
        )

    except:
        raise Exception("Delete Feature Group Failed.")


def add_product_feature_in_grp(company_db_info, feature_group_id, json_obj):
    features_list = json_obj["Features"]

    try:
        add_product_grp_var_queries = []
        add_product_grp_var_params = []

        for feature in features_list:
            insert_grp_feature_query = """
                INSERT INTO TB_SV_PRODUCT_VAR_GRP_INFO(PRODUCT_VAR_GRP_ID, VAR_NM, VAR_DESC, VAR_FORM, IS_PERF_COL, FLAG)
                VALUES (%s, %s, %s, %s, %s, 1);
            """
            insert_grp_feature_param = (
                feature_group_id,
                feature["VAR_NM"],
                feature["VAR_DESC"],
                feature["VAR_FORM"],
                feature["IS_PERF_COL"],
            )

            add_product_grp_var_queries.append(insert_grp_feature_query)
            add_product_grp_var_params.append(insert_grp_feature_param)

        db_utils.execute_modify_query(
            company_db_info,
            add_product_grp_var_queries,
            add_product_grp_var_params,
        )

    except Exception as e:
        raise Exception("Saving Features Failed.")


def update_product_feature_in_grp(company_db_info, feature_group_id, json_obj):
    features_list = json_obj["Features"]

    try:
        update_product_grp_var_queries = []
        update_product_grp_var_params = []

        for feature in features_list:
            update_grp_feature_query = """
                UPDATE TB_SV_PRODUCT_VAR_GRP_INFO
                SET VAR_DESC=%s,
                    VAR_FORM=%s,
                    IS_PERF_COL=%s,
                    FLAG=1
                WHERE PRODUCT_VAR_GRP_ID=%s
                  AND VAR_NM=%s;
            """
            update_grp_feature_param = (
                feature["VAR_DESC"],
                feature["VAR_FORM"],
                feature["IS_PERF_COL"],
                feature_group_id,
                feature["VAR_NM"],
            )

            update_product_grp_var_queries.append(update_grp_feature_query)
            update_product_grp_var_params.append(update_grp_feature_param)

        db_utils.execute_modify_query(
            company_db_info,
            update_product_grp_var_queries,
            update_product_grp_var_params,
        )

    except Exception as e:
        raise Exception("Saving Features Failed.")


def delete_product_feature_in_grp(company_db_info, json_obj):
    product_id = json_obj["ProductId"]
    feature_grp_id = json_obj["FeatureGroupId"]
    features_list = json_obj["Features"]

    try:
        delete_product_grp_feature_queries = []
        delete_product_grp_feature_params = []

        for feature in features_list:
            delete_product_grp_feature_query = """
                DELETE
                FROM TB_SV_PRODUCT_VAR_GRP_INFO
                WHERE PRODUCT_VAR_GRP_ID = %s
                  AND VAR_NM = %s
            """
            delete_product_grp_feature_queries.append(delete_product_grp_feature_query)
            delete_product_grp_feature_params.append((feature_grp_id, feature["VAR_NM"]))

        db_utils.execute_modify_query(
            company_db_info, delete_product_grp_feature_queries, delete_product_grp_feature_params
        )

    except:
        raise Exception("Delete Feature Group Failed.")


def get_product_mart_list(service_db_info, product_id, user_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    select_product_mart_query = """
        SELECT TABLE_ID,
               TABLE_DESC,
               ROW_COUNT,
               COL_COUNT,
               USER_ID,
               ORG_REG_DATE,
               LAST_SAVE_DATE
        FROM TB_SV_DATA
        WHERE PRODUCT_ID = %s
    """

    product_mart_list_json = db_utils.execute_select_query(
        company_db_info, select_product_mart_query, param=(product_id,)
    )

    return product_mart_list_json


def add_product_mart(service_db_info, product_id, mart_table_desc, mart_table_file_nm, delimiter, user_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    try:
        add_product_var_id_query = """
            INSERT INTO TB_SV_DATA(PRODUCT_ID, TABLE_DESC, TABLE_FILE_NM, DELIMITER, USER_ID)
            VALUES(%s, %s, %s, %s, %s);
        """
        add_product_var_id_param = (
            product_id,
            mart_table_desc,
            mart_table_file_nm,
            delimiter,
            user_id,
        )

        set_product_var_id_query = """SET @NEW_PROD_MART_TABLE_ID = LAST_INSERT_ID();"""
        set_product_var_id_param = ()

        add_product_var_queries = [add_product_var_id_query, set_product_var_id_query]
        add_product_var_params = [add_product_var_id_param, set_product_var_id_param]

        select_new_product_mart_table_id = """SELECT @NEW_PROD_MART_TABLE_ID AS PRODUCT_MART_TABLE_ID;"""

        product_mart_id_json = db_utils.execute_modify_query(
            company_db_info,
            add_product_var_queries,
            add_product_var_params,
            select_new_product_mart_table_id,
        )

        if len(product_mart_id_json) == 0:
            raise Exception("Mart not saved successfully.")

    except:
        raise Exception("Saving Mart Failed.")

    return product_mart_id_json


def delete_product_marts(service_db_info, file_server_host, file_server_port, product_id, table_ids, user_id, company_code):
    for table_id in table_ids:
        delete_product_mart(service_db_info, file_server_host, file_server_port, product_id, table_id, company_code)


def delete_product_mart(service_db_info, file_server_host, file_server_port, product_id, table_id, user_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(service_db_info, company_code)
    company_db_info = db_utils.get_company_db_info_from_service_db_info(service_db_info, company_db_name_enc)

    # 1. get mart info before deleting mart
    serving_mart_info = data_utils.serving_get_mart_info(company_db_info, table_id)

    # 2. delete mart from database
    delete_mart_query = """DELETE FROM TB_SV_DATA WHERE TABLE_ID = %s"""
    db_utils.execute_modify_query(company_db_info, delete_mart_query, param=(table_id,))

    # 3. delete file
    select_file_cnt_query = (
        """SELECT TABLE_ID FROM TB_SV_DATA WHERE TABLE_FILE_NM = %s"""
    )
    file_cnt_json = db_utils.execute_select_query(
        company_db_info, select_file_cnt_query, param=(serving_mart_info.mart_file_name,)
    )

    if len(file_cnt_json) == 0:
        data_utils.delete_file(
            file_server_host,
            file_server_port,
            company_code,
            serving_mart_info.mart_file_name,
            constants.FileTypeFlag.SERVING_MART,
        )


def delete_product(service_db_info, company_code, user_id, product_id, file_server_host, file_server_port):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    file_server_host = file_server["HOST"]
    file_server_port = file_server["PORT"]

    # 마트 id
    select_mart_id_query = """
        SELECT TABLE_ID
        FROM TB_SV_DATA
        WHERE PRODUCT_ID = %s
    """
    mart_id_json = db_utils.execute_select_query(
        company_db_info, select_mart_id_query, param=(product_id,)
    )

    # 세그먼트 id
    select_segment_id_query = """
        SELECT SEGMENT_ID
        FROM TB_SV_PRODUCT P
        LEFT JOIN TB_SV_PRODUCT_SEGMENT_HISTORY PSH
               ON P.CURRENT_PROD_HIST_ID = PSH.PRODUCT_HISTORY_ID
        WHERE P.PRODUCT_ID = %s
    """
    segment_id_json = db_utils.execute_select_query(
        company_db_info, select_segment_id_query, param=(product_id,)
    )

    # 항목 id
    select_product_var_id_query = """
        SELECT PRODUCT_VAR_ID
        FROM TB_SV_PRODUCT_VAR_MNG
        WHERE PRODUCT_ID = %s
    """
    product_var_id_json = db_utils.execute_select_query(
        company_db_info, select_product_var_id_query, param=(product_id,)
    )

    # 항목 그룹 id
    select_product_var_group_id_query = """
        SELECT PRODUCT_VAR_GRP_ID
        FROM TB_SV_PRODUCT_VAR_GRP_MNG
        WHERE PRODUCT_VAR_ID = %s
    """
    product_var_group_id_json = db_utils.execute_select_query(
        company_db_info, select_product_var_group_id_query, param=(product_id,)
    )

    product_var_group_id_list = []
    if len(product_var_group_id_json) != 0:
        for x in product_var_group_id_json:
            product_var_group_id_list.append(x["PRODUCT_VAR_GRP_ID"])

    # 마트 삭제
    if len(mart_id_json) != 0:
        for mart_id in mart_id_json:
            delete_product_mart(service_db_info, file_server_host, file_server_port, product_id, mart_id["TABLE_ID"], user_id, company_code)

       # 세그먼트 삭제(+ 모델 삭제)
    for segment_id in segment_id_json:
        if segment_id['SEGMENT_ID'] is not None:
            segment_executor.delete_segment(company_db_info, company_code, product_id, segment_id['SEGMENT_ID'], file_server)

    # 항목(그룹) 삭제
    if len(product_var_id_json) != 0:
        product_var_id = product_var_id_json[0]["PRODUCT_VAR_ID"]

        delete_feature_query = """
            DELETE FROM TB_SV_PRODUCT_VAR_INFO
            WHERE PRODUCT_VAR_ID=%s
        """
        delete_feature_param = (product_var_id,)
        db_utils.execute_modify_query(company_db_info, delete_feature_query, delete_feature_param)

    # 항목 분석(fc) 데이터 삭제
    intermediate_file_set = set()

    select_fine_classing_tasks_query = """
        SELECT PROPERTIES
        FROM TB_SV_LONG_TASK_MNG
        WHERE PRODUCT_ID = %s AND TASK_TYPE = %s
    """
    fc_task_json = db_utils.execute_select_query(company_db_info, select_fine_classing_tasks_query, param=(product_id, "FC"))
    for fc_task in fc_task_json:
        fc_task_properties_json = ast.literal_eval(fc_task["PROPERTIES"])
        if fc_task_properties_json['FcResultFileName'] is not None and fc_task_properties_json['FcResultFileName'] != "":
            intermediate_file_set.add(fc_task_properties_json['FcResultFileName'])

    try:
        for intermediate_file_name in intermediate_file_set:
            data_utils.delete_file(
                file_server_host,
                file_server_port,
                company_code,
                intermediate_file_name,
                constants.FileTypeFlag.INTERMEDIATE_FILE,
            )
    except Exception as e:
        pass

    if len(product_var_group_id_list) != 0:
        delete_feature_group_queries = []
        delete_feature_group_params = []
        for product_var_group_id in product_var_group_id_list:
            delete_feature_group_query = """
                DELETE FROM TB_SV_PRODUCT_VAR_GRP_INFO
                WHERE PRODUCT_VAR_GRP_ID=%s
            """
            delete_feature_group_param = (product_var_group_id,)
            delete_feature_group_queries.append(delete_feature_group_query)
            delete_feature_group_params.append(delete_feature_group_param)
        db_utils.execute_modify_query(company_db_info, delete_feature_group_queries, delete_feature_group_params)

    # 상품 삭제
    delete_product_queries = []
    delete_product_params = []

    delete_product_segment_history_query = """
        DELETE FROM TB_SV_PRODUCT_SEGMENT_HISTORY
        WHERE PRODUCT_ID = %s
    """
    delete_product_segment_history_params = (product_id,)
    delete_product_queries.append(delete_product_segment_history_query)
    delete_product_params.append(delete_product_segment_history_params)

    delete_product_info_query = """
        DELETE FROM TB_SV_PRODUCT
        WHERE PRODUCT_ID = %s
    """
    delete_product_info_param = (product_id,)
    delete_product_queries.append(delete_product_info_query)
    delete_product_params.append(delete_product_info_param)

    db_utils.execute_modify_query(company_db_info, delete_product_queries, delete_product_params)


def upload_data(
    company_db_info,
    company_code,
    user_id,
    root_dir,
    result_file_path_faf,
    done_file_path_faf,
    meta_json,
    raw_mart_file_path,
    file_server_host,
    file_server_port,
    external_purpose,
):
    # auth_key = meta_json["AuthKey"]
    product_id = meta_json["ProductId"]
    mart_name = meta_json["MartName"]
    mart_description = meta_json["MartDescription"]
    delimiter = meta_json["Delimiter"]
    visible = meta_json["Visible"]
    # is_perf_column_dict = meta_json['IsPerfColumnDict']
    # [2020-05-08] pjh - related flow list
    # related_flow_list = meta_json['RelatedFlowList']

    # [2020-09-16] pjh - disable data upload is for external use and user auth level is 2 or 3
    # auth_level = db_utils.get_auth_level(db_info=company_db_info, user_id=user_id)
    # if external_purpose and auth_level > 1:
    #     raise Exception("Only administrator can upload data")
    # else:
    #     mart_name_prefix = "_".join(mart_name.split("_")[1:-1])
    #     _authorize_user_mart_modification(
    #         user_id, company_db_info, mart_name_prefix, auth_level
    #     )

    select_mart_query = """SELECT TABLE_ID FROM TB_SV_DATA WHERE TABLE_ID = %s AND PRODUCT_ID = %s"""
    mart_id_json = db_utils.execute_select_query(
        db_info=company_db_info, query=select_mart_query, param=(mart_name, product_id)
    )

    if len(mart_id_json) > 0:
        raise Exception("The mart {0} for product {1} already exists!".format(mart_name, product_id))

    # read csv -> processing(add system key, ...)
    df = pd.DataFrame()
    supported_enc_types = ["utf-8-sig", "cp949"]
    cur_idx = 0
    cols_cnt = 0
    rows_cnt = 0
    temp_parquet_mart_file_path = common_utils.make_temp_file()
    for cur_idx, enc in enumerate(supported_enc_types):
        try:
            with pd.read_csv(
                raw_mart_file_path,
                sep=delimiter,
                index_col=False,
                dtype="object",
                encoding=enc,
                chunksize=100000,
            ) as reader:
                for i, chunk in enumerate(reader):
                    if i == 0:
                        cols_cnt = len(chunk.columns)
                        chunk.to_parquet(path=temp_parquet_mart_file_path, engine='fastparquet', index=False)
                    else:
                        chunk.to_parquet(path=temp_parquet_mart_file_path, engine='fastparquet', index=False, append=True)
                    rows_cnt += len(chunk)
            break
        except UnicodeDecodeError:
            # no encoding has been succeeded
            if cur_idx == len(supported_enc_types) - 1:
                raise Exception(
                    "The file in server may contain Hangeul or unicode character that cannot be decoded. "
                    "Please convert file encoding to cp949 or utf-8 or remove Hangeul or unicode character."
                )
        except Exception:
            raise

    new_mart_file_name = data_utils.upload_file_or_bytes(
        file_server_host,
        file_server_port,
        company_code,
        temp_parquet_mart_file_path,
        constants.FileTypeFlag.SERVING_MART,
    )

    os.remove(temp_parquet_mart_file_path)

    # [2022-12-15] syg - set all columns to 0 (flow has performance columns' name)
    is_perf_column_dict = {k: 0 for k in df.columns}

    # update mart meta
    _update_mart_meta(
        company_db_info=company_db_info,
        product_id=product_id,
        mart_name=mart_name,
        mart_description=mart_description,
        user_id=user_id,
        rows_cnt=rows_cnt,
        cols_cnt=cols_cnt,
        data_file_name=new_mart_file_name,
        delimiter=delimiter,
        visible=visible,
        is_perf_column_dict=is_perf_column_dict,
    )

    # write row count to the result file
    with open(result_file_path_faf, "w") as rfd, open(done_file_path_faf, "w") as dfd:
        rfd.write(str(rows_cnt))
        dfd.write(constants.FAF_DONE_STRING)


# [2026-06-19] dyk - server repository 경로 목록 불러오기
def get_server_repository_dirs(root_dir, user_id, company_code):
    server_repository = os.path.join(root_dir, constants.SERVER_REPOSITORY_NAME)
    nserving_user_path = os.path.join(server_repository, company_code, user_id)
    if not os.path.exists(nserving_user_path):
        os.makedirs(nserving_user_path)
    server_dir_json = [
        {"DIR_NAME": "nserving-server", "DIR_PATH": ""}
    ]
    return server_dir_json


# [2026-06-19] dyk - server repository 경로의 파일 목록 불러오기
def get_server_repository_files(root_dir, user_id, company_code, selected_dirs):
    # 파일 목록 반환 시 불포함할 파일 명 리스트
    ignored_names = []

    server_repository = os.path.join(root_dir, constants.SERVER_REPOSITORY_NAME)
    dir_path = os.path.join(server_repository, *selected_dirs)

    file_info_list = []
    if os.path.exists(dir_path):
        for file_name in os.listdir(dir_path):
            if not file_name.startswith(".") and file_name not in ignored_names:
                file_path = os.path.join(dir_path, file_name)
                file_info = {
                    "FILE_NM": file_name,
                    "FILE_SIZE": os.path.getsize(file_path),
                }
                last_modified_timestamp = os.path.getmtime(file_path)
                last_modified_datetime = datetime.datetime.fromtimestamp(
                    last_modified_timestamp
                )
                last_modified_date = last_modified_datetime.strftime("%Y-%m-%d")
                file_info["LAST_MODIFIED_DATE"] = last_modified_date
                if os.path.isfile(file_path):
                    file_info["IS_FILE"] = 1
                    file_ext = os.path.splitext(file_name)[1]
                    file_info["EXTENSION"] = file_ext[1:] if file_ext != "" else ""
                else:
                    file_info["IS_FILE"] = 0
                    file_info["EXTENSION"] = ""
                file_info_list.append(file_info)

    return file_info_list


def upload_data_from_server(
    company_db_info,
    company_code,
    user_id,
    root_dir,
    result_file_path_faf,
    done_file_path_faf,
    meta_json,
    file_server_host,
    file_server_port,
):
    data_file_name = meta_json["DataFileName"]
    mart_name = meta_json["MartName"]
    mart_description = meta_json["MartDescription"]
    delimiter = meta_json["Delimiter"]
    product_id = meta_json["ProductId"]

    # 마트 명 유효성 확인
    select_mart_query = """SELECT TABLE_ID FROM TB_SV_DATA WHERE TABLE_ID = %s"""
    mart_id_json = db_utils.execute_select_query(
        db_info=company_db_info, query=select_mart_query, param=(mart_name,)
    )
    if len(mart_id_json) > 0:
        raise Exception("The mart {0} already exists!".format(mart_name))

    # 데이터 파일 경로
    data_file_path = os.path.join(
        root_dir, constants.SERVER_REPOSITORY_NAME, data_file_name
    )

    # read csv -> processing(add system key, ...)
    df = pd.DataFrame()
    supported_enc_types = ["utf-8-sig", "cp949"]
    cur_idx = 0
    cols_cnt = 0
    rows_cnt = 0
    for cur_idx, enc in enumerate(supported_enc_types):
        try:
            df = pd.read_csv(
                data_file_path,
                sep=delimiter,
                index_col=False,
                dtype="object",
                encoding=enc,
            )
            cols_cnt = len(df.columns)
            rows_cnt = len(df)
            break
        except UnicodeDecodeError:
            # no encoding has been succeeded
            if cur_idx == len(supported_enc_types) - 1:
                raise Exception(
                    "The file in server may contain Hangeul or unicode character that cannot be decoded. "
                    "Please convert file encoding to cp949 or utf-8 or remove Hangeul or unicode character."
                )
        except Exception:
            raise

    # [2019-03-04] pjh - convert to parquet
    temp_parquet_mart_file_path = common_utils.make_temp_file()
    df.to_parquet(path=temp_parquet_mart_file_path, engine="pyarrow", index=False)
    new_mart_file_name = data_utils.upload_file_or_bytes(
        file_server_host,
        file_server_port,
        company_code,
        temp_parquet_mart_file_path,
        constants.FileTypeFlag.SERVING_MART,
    )

    os.remove(temp_parquet_mart_file_path)

    # [2022-12-15] syg - set all columns to 0 (flow has performance columns' name)
    is_perf_column_dict = {k: 0 for k in df.columns}

    # update mart meta
    _update_mart_meta(
        company_db_info=company_db_info,
        product_id=product_id,
        mart_name=mart_name,
        mart_description=mart_description,
        user_id=user_id,
        rows_cnt=rows_cnt,
        cols_cnt=cols_cnt,
        data_file_name=new_mart_file_name,
        delimiter=delimiter,
        visible=visible,
        is_perf_column_dict=is_perf_column_dict,
    )

    # write row count to the result file
    with open(result_file_path_faf, "w") as rfd, open(done_file_path_faf, "w") as dfd:
        rfd.write(str(rows_cnt))
        dfd.write(constants.FAF_DONE_STRING)


# [2021-07-06] dyk - upload query result
def upload_query_result(
    company_db_info,
    company_code,
    user_id,
    result_file_path_faf,
    done_file_path_faf,
    meta_json,
    file_server_host,
    file_server_port,
):
    mart_name = meta_json["MartName"]
    mart_description = meta_json["MartDescription"]
    # 일단 postgresql만 테스트
    db_type = meta_json["DbType"]
    query = meta_json["Query"]
    product_id = meta_json["ProductId"]

    # 마트 명 유효성 확인
    select_mart_query = """SELECT TABLE_ID FROM TB_SV_DATA WHERE TABLE_ID = %s"""
    mart_id_json = db_utils.execute_select_query(
        db_info=company_db_info, query=select_mart_query, param=(mart_name,)
    )

    if len(mart_id_json) > 0:
        raise Exception("The mart {0} already exists!".format(mart_name))

    # TODO 연결할 db 정보(임시로 하드코딩)
    psql_db_info = constants.DbInfo(
        db_host="10.94.30.143",
        db_port="60006",
        db_user="postgres",
        db_pw_enc=crypto_utils.encrypt("user00!!"),
        db_name_enc=crypto_utils.encrypt("postgres"),
    )

    # 쿼리 실행
    try:
        query = query.replace("\\n", "\n")
        query_result_rows, query_result_columns = db_utils.execute_query_psql(
            psql_db_info, query
        )
        rows_cnt = len(query_result_rows)
        cols_cnt = len(query_result_columns)

        # 쿼리 실행 결과 DataFrame
        result_df = pd.DataFrame(query_result_rows, columns=query_result_columns)

        # 쿼리 결과를 parquet으로 변환하여 파일 서비스에 저장
        temp_parquet_mart_file_path = common_utils.make_temp_file()
        result_df.to_parquet(
            temp_parquet_mart_file_path, engine="pyarrow", index=False
        )

        new_mart_file_name = data_utils.upload_file_or_bytes(
            file_server_host,
            file_server_port,
            company_code,
            temp_parquet_mart_file_path,
            constants.FileTypeFlag.SERVING_MART,
        )

        os.remove(temp_parquet_mart_file_path)

        # target column 은 우선 모두 0으로 설정 하고, 데이터 수정 에서 설정 하도록 구현
        is_perf_column_dict = {k: 0 for k in result_df.columns}

    update_mart_meta_queries = [update_mart_meta_query]
    update_mart_meta_params = [
        (
            mart_name,
            product_id,
            mart_description,
            rows_cnt,
            cols_cnt,
            user_id,
            data_file_name,
            delimiter,
            visible,
        ),
        # param_list,
    ]

    db_utils.execute_modify_query(
        company_db_info, query=update_mart_meta_queries, param=update_mart_meta_params
    )


# [2020-06-05] pjh - modify server repository file name
def modify_server_repository_file_name(service_db_info, root_dir, json_obj):
    auth_key = json_obj["AuthKey"]
    dir_path = json_obj["DirPath"]
    from_file_name = json_obj["FromFileName"]
    to_file_name = json_obj["ToFileName"]

    company_and_user_info = db_utils.get_company_and_user_info(
        service_db_info, auth_key
    )
    company_code = company_and_user_info.company_code
    user_id = company_and_user_info.user_id

    server_repository = os.path.join(
        root_dir, constants.SERVER_REPOSITORY_NAME, company_code, user_id
    )

    # move file
    to_file_path = os.path.join(server_repository, *dir_path, to_file_name)
    if os.path.exists(to_file_path):
        raise Exception("The file already exists!")

    from_file_path = os.path.join(server_repository, *dir_path, from_file_name)
    # if os.path.isfile(from_file_path):
    os.rename(from_file_path, to_file_path)


# [2020-06-05] pjh - delete server repository file name
def delete_server_repository_file_name(service_db_info, root_dir, auth_key, file_name):
    company_and_user_info = db_utils.get_company_and_user_info(
        service_db_info, auth_key
    )
    company_code = company_and_user_info.company_code
    user_id = company_and_user_info.user_id

    server_repository = os.path.join(
        root_dir, constants.SERVER_REPOSITORY_NAME, company_code, user_id
    )
    # if not os.path.exists(server_repository):
    #     os.makedirs(server_repository)

    file_path = os.path.join(server_repository, file_name)
    if os.path.isfile(file_path):
        os.remove(file_path)


def get_product_detail(service_db_info, product_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    select_product_detail_query = """
        SELECT PRODUCT_ID,
               1 AS PRODUCT_TYPE,
               CURRENT_PROD_HIST_ID AS PRODUCT_HISTORY_ID,
               PRODUCT_NAME,
               PRODUCT_DETAIL AS PRODUCT_SHORT_DESC,
               PRODUCT_MEMO AS PRODUCT_LONG_DESC,
               USER_ID AS OWNER_ID,
               ENROLLED_DATETIME,
               LAST_MODIFIED_DATETIME
        FROM TB_SV_PRODUCT
        WHERE PRODUCT_ID = %s
    """

    product_detail_list_json = db_utils.execute_select_query(
        company_db_info, select_product_detail_query, param=(product_id,)
    )

    # TODO MEMBER 정보 저장 및 처리
    product_detail_list_json[0]["MEMBER"] = [
        {"USER_ID": "admin", "PRODUCT_MEMBER_ROLE": 0},
        {"USER_ID": "reader1", "PRODUCT_MEMBER_ROLE": 3},
        {"USER_ID": "editor1", "PRODUCT_MEMBER_ROLE": 1},
    ]

    # SEGMENTS
    select_product_segment_query = """
        SELECT
            S.SEGMENT_ID,
            S.SEGMENT_NAME,
            S.SEGMENT_DETAIL
        FROM TB_SV_PRODUCT_SEGMENT_HISTORY PSH
        LEFT JOIN TB_SV_SEGMENT_HISTORY SH
               ON PSH.SEGMENT_HISTORY_ID = SH.HISTORY_ID
        LEFT JOIN TB_SV_SEGMENT S
               ON SH.SEGMENT_ID = S.SEGMENT_ID
        WHERE PSH.PRODUCT_HISTORY_ID =
            (SELECT CURRENT_PROD_HIST_ID FROM TB_SV_PRODUCT
             WHERE PRODUCT_ID = %s)
    """

    product_segment_json = db_utils.execute_select_query(
        company_db_info, select_product_segment_query, param=(product_id,)
    )

    if not product_segment_json:
        product_segment_json = []

    product_detail_list_json[0]["SEGMENTS"] = product_segment_json

    return product_detail_list_json[0]


def get_product_history_list(service_db_info, product_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    select_product_history_list_query = """
        SELECT PH.HISTORY_ID AS PRODUCT_HISTORY_ID,
               PH.HISTORY_TYPE AS PRODUCT_HISTORY_TYPE,
               LAG(PH.HISTORY_ID) OVER(PARTITION BY PH.PRODUCT_ID ORDER BY PH.HISTORY_ID) AS PREV_HISTORY_ID,
               PH.HISTORY_NAME,
               PH.HISTORY_DETAIL,
               PH.ENROLLED_DATETIME
        FROM TB_SV_PRODUCT P
        LEFT JOIN TB_SV_PRODUCT_HISTORY PH
               ON P.PRODUCT_ID = PH.PRODUCT_ID
        WHERE P.PRODUCT_ID = %s
          AND PH.HISTORY_ID IS NOT NULL
        ORDER BY PH.HISTORY_ID DESC
    """

    product_history_list_json = db_utils.execute_select_query(
        company_db_info, select_product_history_list_query, param=(product_id,)
    )

    return product_history_list_json


def get_product_history_details(service_db_info, product_history_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    select_product_history_query = """
        SELECT
            A.PRODUCT_ID,
            A.PRODUCT_HISTORY_ID,
            A.PRODUCT_HISTORY_TYPE,
            A.PREV_HISTORY_ID,
            A.HISTORY_NAME,
            A.HISTORY_DETAIL,
            A.SEGMENT_COLUMN,
            A.EXCLUSION_COLUMN,
            A.ENROLLED_DATETIME,
            A.USER_ID
        FROM
        (SELECT
            PH.PRODUCT_ID,
            PH.HISTORY_ID AS PRODUCT_HISTORY_ID,
            PH.HISTORY_TYPE AS PRODUCT_HISTORY_TYPE,
            LAG(PH.HISTORY_ID) OVER(PARTITION BY PH.PRODUCT_ID ORDER BY PH.HISTORY_ID) AS PREV_HISTORY_ID,
            PH.HISTORY_NAME,
            PH.HISTORY_DETAIL,
            PH.SEGMENT_VAL_NM AS SEGMENT_COLUMN,
            PH.EXCLUSION_VAL_NM AS EXCLUSION_COLUMN,
            PH.ENROLLED_DATETIME,
            P.USER_ID
        FROM TB_SV_PRODUCT_HISTORY PH
        LEFT JOIN TB_SV_PRODUCT P
               ON PH.PRODUCT_ID = P.PRODUCT_ID
        WHERE A.PRODUCT_HISTORY_ID = %s
    """

    product_history_details_json = db_utils.execute_select_query(
        company_db_info, select_product_history_query, param=(product_history_id,)
    )

    for product_history_detail in product_history_details_json:
        if not "SEGMENTS" in product_history_detail:
            product_history_detail["SEGMENTS"] = []

        product_id = product_history_detail.pop("PRODUCT_ID") if product_history_detail else None

        # TODO 1) REVERSE_PROB 을 MODEL 로 이동 2) Target 정보 넣기
        if product_id:
            select_product_history_segment_query = """
                SELECT SH.SEGMENT_ID,
                       PSH.SEGMENT_HISTORY_ID,
                       S.SEGMENT_NAME,
                       S.SEGMENT_DETAIL,
                       SH.SEGMENT_VALUE,
                       SH.EXCLUSION_VALUE,
                       SH.PDO,
                       SH.ANCHOR,
                       SH.MAPPING_ID,
                       SH.GRADE_ID,
                       'BAD' AS TARGET,
                       0 AS REVERSE_PROB
                FROM TB_SV_PRODUCT_SEGMENT_HISTORY PSH
                LEFT JOIN TB_SV_SEGMENT_HISTORY SH
                       ON PSH.SEGMENT_HISTORY_ID = SH.HISTORY_ID
                LEFT JOIN TB_SV_SEGMENT S
                       ON SH.SEGMENT_ID = S.SEGMENT_ID
                WHERE PSH.PRODUCT_HISTORY_ID = %s
            """

            product_history_segment_jsons = db_utils.execute_select_query(
                company_db_info, select_product_history_segment_query, param=(product_history_id,)
            )

            for product_history_segment_json in product_history_segment_jsons:
                if not "MODELS" in product_history_segment_json:
                    product_history_segment_json["MODELS"] = []

                product_history_detail["SEGMENTS"].append(product_history_segment_json)

                # TODO - pop ?
                # segment_id = product_history_segment_json.pop("SEGMENT_ID") if product_history_segment_json else None
                segment_id = product_history_segment_json["SEGMENT_ID"] if product_history_segment_json else None
                if segment_id:
                    select_product_history_segment_model_query = """
                        SELECT M.MODEL_ID,
                               M.MODEL_NAME,
                               M.MODEL_DETAIL,
                               SMH.MODEL_HISTORY_ID,
                               M.MODEL_TYPE,
                               MH.MODEL_FILE_NAME,
                               MH.WEIGHT,
                               MH.REVERSE_PROB
                        FROM TB_SV_MODEL M, TB_SV_SEGMENT_MODEL_HISTORY SMH, TB_SV_MODEL_HISTORY MH, TB_SV_SEGMENT S
                        WHERE SMH.SEGMENT_ID = %s
                          AND SMH.SEGMENT_ID = S.SEGMENT_ID
                          AND SMH.SEGMENT_HISTORY_ID = S.CURRENT_SEG_HIST_ID
                          AND SMH.MODEL_ID = M.MODEL_ID
                          AND SMH.MODEL_HISTORY_ID = MH.HISTORY_ID
                    """

                    product_history_segment_model_json = db_utils.execute_select_query(
                        company_db_info, select_product_history_segment_model_query, param=(segment_id,)
                    )

                    if len(product_history_segment_model_json) != 0:
                        product_history_segment_json["MODELS"] = product_history_segment_model_json

            for product_history_segment_json in product_history_segment_jsons:
                product_history_segment_json["CALIBRATION"] = []

                if (product_history_segment_json["MAPPING_ID"] is not None 
                    and product_history_segment_json["MAPPING_ID"] > 0):
                    select_product_history_segment_calibration_query = """
                        SELECT GREATEST(MIN_CLOSED, 0) AS SCORE, MIN_CLOSED_MAP AS MAPPED_SCORE
                        FROM TB_SV_SEGMENT_CALIBRATION_INFO
                        WHERE MAPPING_ID = %s
                        ORDER BY MIN_CLOSED
                    """

                    product_history_segment_calibration_json = db_utils.execute_select_query(
                        company_db_info, select_product_history_segment_calibration_query,
                        param=(product_history_segment_json["MAPPING_ID"],)
                    )

                    product_history_segment_json["CALIBRATION"] = product_history_segment_calibration_json

            for product_history_segment_json in product_history_segment_jsons:
                product_history_segment_json["GRADE"] = []
                if (product_history_segment_json["GRADE_ID"] is not None 
                    and product_history_segment_json["GRADE_ID"] > 0):
                    select_product_history_segment_grade_query = """
                        SELECT GRADE, LOWER AS MIN, UPPER AS MAX
                        FROM TB_SV_SEGMENT_GRADE_INFO
                        WHERE GRADE_ID = %s
                        ORDER BY GRADE
                    """

                    product_history_segment_grade_json = db_utils.execute_select_query(
                        company_db_info, select_product_history_segment_grade_query,
                        param=(product_history_segment_json["GRADE_ID"],)
                    )

                    product_history_segment_json["GRADE"] = product_history_segment_grade_json

    return product_history_details_json[0]


def modify_product_column(company_db_info, json_obj):
    product_id = json_obj["ProductId"]
    old_product_history_id = json_obj["ProductHistoryId"]
    segment_val_name = json_obj["SegmentColumn"]
    exclusion_val_nm = json_obj["ExclusionColumn"]

    update_product_column_queries, update_product_column_params = [], []

    add_product_history_query = """
        INSERT INTO TB_SV_PRODUCT_HISTORY(PRODUCT_ID, HISTORY_NAME, HISTORY_DETAIL, HISTORY_TYPE, SEGMENT_VAL_NM, EXCLUSION_VAL_NM)
        VALUES(%s, %s, %s, %s, %s, %s);
    """
    add_product_history_param = (product_id, "MODIFY CONDITION COLUMN", "조건 컬럼 변경", "UPDATE", segment_val_name, exclusion_val_nm)

    update_product_column_queries.append(add_product_history_query)
    update_product_column_params.append(add_product_history_param)

    set_product_history_id_query = """SET @NEW_PROD_HIST_ID = LAST_INSERT_ID();"""
    set_product_history_id_param = ()

    update_current_history_id_query = """
        UPDATE TB_SV_PRODUCT
        SET CURRENT_PROD_HIST_ID = @NEW_PROD_HIST_ID
        WHERE PRODUCT_ID = %s;
    """
    update_current_history_id_param = (product_id,)

    update_product_column_queries.append(set_product_history_id_query)
    update_product_column_params.append(set_product_history_id_param)
    update_product_column_queries.append(update_current_history_id_query)
    update_product_column_params.append(update_current_history_id_param)

    select_new_product_history_id = """SELECT LAST_INSERT_ID() AS PRODUCT_HISTORY_ID;"""

    new_product_history_id_json = db_utils.execute_modify_query(
        db_info=company_db_info, query=update_product_column_queries,
        param=update_product_column_params,
        select_query=select_new_product_history_id
    )

    if len(new_product_history_id_json) == 0:
        raise Exception("Condition columns not modified successfully.")

    # product_history_id 업데이트 전 가장 최근 segment 정보 불러오기
   
        get_current_segment_info_query = """
        SELECT SEGMENT_ID, SEGMENT_HISTORY_ID
        FROM TB_SV_PRODUCT_SEGMENT_HISTORY
        WHERE PRODUCT_ID = %s AND PRODUCT_HISTORY_ID=%s;
    """
    get_current_segment_info_param = (product_id, old_product_history_id)
    current_segment_info_json = db_utils.execute_select_query(db_info=company_db_info, query=get_current_segment_info_query,
                                                            param=get_current_segment_info_param)

    # 새로운 product_history_id
    new_product_history_id = int(new_product_history_id_json[0]["PRODUCT_HISTORY_ID"])

    # product segment history 업데이트
    for current_segment_info in current_segment_info_json:
        segment_id = current_segment_info["SEGMENT_ID"] if current_segment_info["SEGMENT_ID"] else None
        segment_history_id = current_segment_info["SEGMENT_HISTORY_ID"] if current_segment_info["SEGMENT_HISTORY_ID"] else None

        add_product_segment_history_query = """
            INSERT INTO TB_SV_PRODUCT_SEGMENT_HISTORY(PRODUCT_ID, PRODUCT_HISTORY_ID, SEGMENT_ID, SEGMENT_HISTORY_ID)
            VALUES (%s, %s, %s, %s);
        """
        add_product_segment_history_param = (product_id, new_product_history_id, segment_id, segment_history_id)
        # 기존 세그먼트를 업데이트된 상품 히스토리에 추가
        db_utils.execute_modify_query(
            db_info=company_db_info,
            query=add_product_segment_history_query,
            param=add_product_segment_history_param,
        )


    return {'PRODUCT_HISTORY_ID': new_product_history_id}


def modify_product_detail(company_db_info, product_id, json_obj):
    # 상품 short description 수정
    product_detail = json_obj["ProductDetail"]

    modify_product_detail_queries, modify_product_detail_params = [], []

    modify_product_detail_query = """
        UPDATE
            TB_SV_PRODUCT
        SET
            PRODUCT_DETAIL = %s
        WHERE
            PRODUCT_ID = %s
    """

    modify_product_detail_param = (product_detail, product_id)

    modify_product_detail_queries.append(modify_product_detail_query)
    modify_product_detail_params.append(modify_product_detail_param)

    db_utils.execute_modify_query(
        company_db_info, query=modify_product_detail_queries, param=modify_product_detail_params
    )


def get_product_task_list(company_db_info, product_name, task_type, status, executor_id):
    # long task list 조회(task_id, product_name, task_type, enrolled_datetime, finished_datetime, executer_id, status)
    select_long_task_list_query = """
        SELECT LTM.TASK_ID, P.PRODUCT_NAME, LTM.TASK_TYPE, LTM.ENROLLED_DATETIME,
               LTM.FINISHED_DATETIME, LTM.USER_ID, LTM.STATUS
        FROM TB_SV_LONG_TASK_MNG_LTM
        LEFT JOIN TB_SV_PRODUCT P
             ON LTM.PRODUCT_ID = P.PRODUCT_ID
    """

    select_long_task_list_param = []

    conditions = []
    if product_name is not None:
        conditions.append("P.PRODUCT_NAME = %s")
        select_long_task_list_param.append(product_name)

    if task_type is not None:
        conditions.append("LTM.TASK_TYPE = %s")
        select_long_task_list_param.append(task_type)

    if executor_id is not None:
        conditions.append("LTM.USER_ID = %s")
        select_long_task_list_param.append(executor_id)

    if status is not None:
        conditions.append("LTM.STATUS = %s")
        select_long_task_list_param.append(status)

    if conditions:
        select_long_task_list_query += " WHERE " + " AND ".join(conditions)

    long_task_list_json = db_utils.execute_select_query(
        company_db_info, select_long_task_list_query, tuple(select_long_task_list_param)
    )

    return long_task_list_json


def get_product_task_error(company_db_info, task_id):
    # error 파일 경로
    select_task_error_file_query = """
        SELECT ERROR_FILE_NAME
        FROM TB_SV_LONG_TASK_MNG
        WHERE TASK_ID=%s
    """

    select_task_error_file_param = (task_id, )

    task_error_file_json = db_utils.execute_select_query(
        company_db_info, select_task_error_file_query, select_task_error_file_param
    )

    # error 메시지
    task_error_file_path = task_error_file_json[0]["ERROR_FILE_NAME"]
    with open(task_error_file_path, 'r') as f:
        error_msg = f.read()

    # error_msg = error_msg.replace("\\"", "\"")
    error_msg_json = [{"ERROR_MSG": error_msg}]

    return error_msg_json


def get_segment_list(service_db_info, product_ids, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    select_segment_list_query = """
        SELECT
            S.SEGMENT_ID, S.CURRENT_SEG_HIST_ID, S.SEGMENT_NAME, S.SEGMENT_DETAIL,
            COUNT(SMH.SEGMENT_ID) AS MODEL_CNT,
            S.LAST_MODIFIED_DATETIME
        FROM TB_SV_PRODUCT_SEGMENT_HISTORY PSH
        LEFT JOIN TB_SV_SEGMENT_HISTORY SH
            ON PSH.SEGMENT_HISTORY_ID = SH.HISTORY_ID
        LEFT JOIN TB_SV_SEGMENT S
            ON SH.SEGMENT_ID = S.SEGMENT_ID
        LEFT JOIN TB_SV_SEGMENT_MODEL_HISTORY SMH
            ON S.CURRENT_SEG_HIST_ID = SMH.SEGMENT_HISTORY_ID
        WHERE PSH.PRODUCT_HISTORY_ID =
            (SELECT CURRENT_PROD_HIST_ID FROM TB_SV_PRODUCT
                WHERE PRODUCT_ID IN ({0}))
        GROUP BY
            S.SEGMENT_ID, S.SEGMENT_NAME, S.SEGMENT_DETAIL, S.LAST_MODIFIED_DATETIME;
    """.format(
        ",".join(product_ids.split(" "))
    )

    try :
        product_segment_json = db_utils.execute_select_query(
            company_db_info, select_segment_list_query, ( )
        )
        if not product_segment_json:
            product_segment_json = []
    except Exception as e:
        product_segment_json = []

    return product_segment_json


def get_base_yn_list(service_db_info, product_id, company_code):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    # TODO - User, Auth 관련 처리 검토 (기존 코드 참고)

    select_history_base_ym_query = """
        SELECT
            S.SEGMENT_ID, HISTORY_ID, history.BASE_YM AS BASE_YM
        FROM
            TB_SV_FLOW_HISTORY_MNG history
        INNER JOIN
            TB_SV_SEGMENT S
        ON history.SEGMENT_ID = S.SEGMENT_ID
        WHERE
            S.PRODUCT_ID = %s
            AND history.TASK_YN = 1
            AND history.BASE_YM IS NOT NULL
            AND history.BASE_YM <> ""
        ORDER BY
            BASE_YM DESC
    """

    try :
        history_base_ym_json = db_utils.execute_select_query(
            company_db_info, select_history_base_ym_query, (product_id)
        )
        if not history_base_ym_json:
            history_base_ym_json = []
    except Exception as e:
        history_base_ym_json = []

    return history_base_ym_json


def get_segment_perf_history_list(service_db_info, json_obj):
    # service_db_info, company_db_name_enc
    # )
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, json_obj["CompanyCode"]
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    segment_id = json_obj["SegmentId"]
    base_only = json_obj["BaseOnly"]
    segment_flag = json_obj["SegmentFlag"] if json_obj.get("SegmentFlag") else -1

    if base_only:
        comp_columns = ""
    else:
        comp_columns = """, COMP_KS, COMP_AUROC,
            COMP_GINI, COMP_PSI, IF(history.COMPARE_PRED_FILE_NAME = '', 0, 1) AS HAS_COMP_MODEL"""

    # [2020-07-03] pjh - add IS_ONLINE_HIST
    if segment_flag < 0:
        segment_flag_condition = ""
    else:
        cond = "(SELECT DISTINCT FLOW_PREDICT_ID FROM TB_SV_MODEL_HISTORY_MNG WHERE FLOW_PREDICT_ID IS NOT NULL)"
        if segment_flag == 1:
            segment_flag_condition = "AND perf_history.HISTORY_ID IN " + cond
        else:
            segment_flag_condition = "AND perf_history.HISTORY_ID NOT IN " + cond

    get_segment_ensemble_perf_history_list_query = """
        SELECT
            ROW_NUMBER() OVER(ORDER BY history.HISTORY_ORDER) AS HISTORY_ORDER,
            history.HISTORY_ID, history.HISTORY_NAME, history.HISTORY_DETAIL,
            history.FLOW_HISTORY_ID, history.COMPARE_FLOW_HISTORY_ID, history.ENROLLED_DATETIME,
            KS, AUROC, GINI, PSI{0}
        FROM
            TB_SV_FLOW_PREDICT_ENSEMBLE_PERF_HISTORY perf_history
        LEFT JOIN
            TB_SV_FLOW_HISTORY_MNG history
        ON perf_history.HISTORY_ID = history.HISTORY_IDWlrma_rkf
        WHERE
            history.FLOW_ID = %s
            {1}
        ORDER BY
            history.HISTORY_ORDER
    """.format(
        *args: comp_columns, segment_flag_condition
    )

    try:
        segment_ensemble_perf_history_list_json = db_utils.execute_select_query(
            company_db_info, get_segment_ensemble_perf_history_list_query, param=(segment_id,)
        )
        if not segment_ensemble_perf_history_list_json:
            segment_ensemble_perf_history_list_json = []
    except Exception as e:
        segment_ensemble_perf_history_list_json = []

    return segment_ensemble_perf_history_list_json


# [2023-01-04] ldk - add upload mart into database in Windows version ML.
def upload_mart_to_db(
    service_db_info,
    root_dir,
    result_file_path_faf,
    done_file_path_faf,
    meta_json,
    raw_mart_file_path,
    file_server_host,
    file_server_port,
    external_purpose,
):
    auth_key = meta_json["AuthKey"]
    # mysql is 3-layer database so there is no schema in a database. use prefix to avoid main tables being dropped.
    meta_json["MartName"] = "_" + meta_json["MartName"]
    mart_name = meta_json["MartName"]
    mart_description = meta_json["MartDescription"]
    delimiter = meta_json["Delimiter"]
    domain_json = meta_json["DomainJson"]
    svd_json = meta_json["SvdJson"]
    variable_json = meta_json["VariableJson"]
    variable_json = meta_json["VariableJson"]
    except_columns = meta_json["ExceptColumns"]
    # fire and forget files
    client_polling_dir = os.path.join(root_dir, constants.CLIENT_POLLING_DIR_NAME)
    check_all_rows_to_infer_type = meta_json["CheckAllRowsToInferType"]
    do_data_profile = meta_json["DoDataProfile"]
    has_header = meta_json["HasHeader"]

    company_and_user_info = db_utils.get_company_and_user_info(
        service_db_info=service_db_info, auth_key=auth_key
    )
    db_name_enc = company_and_user_info.company_db_name_enc
    company_code = company_and_user_info.company_code
    user_id = company_and_user_info.user_id
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info=service_db_info, company_db_name_enc=db_name_enc
    )

    # [2020-09-16] pjh - disable mart upload when app is for external use and user auth level is 2 or 3
    # auth_level = get_auth_level(db_info=company_db_info, user_id=user_id)
    # if external_purpose and auth_level > 1:
    #     raise Exception("Only administrator can upload mart")

    # [2018-09-07] pjh - upload data except void column
    new_variable_json = []
    for var_info in variable_json:
        if var_info["VAR_NM"] not in except_columns:
            new_variable_json.append(var_info)

    if len(new_variable_json) == 0:
        raise Exception("There is no data.")

    new_mart_file_path = common_utils.make_temp_file()
    supported_enc_types = ["utf-8-sig", "cp949"]
    try:
        rows_cnt = 0
        for cur_idx, enc in enumerate(supported_enc_types):
            try:
                new_variable_json, rows_cnt = process_uploaded_mart_to_db(
                    mart_csv_file_path=raw_mart_file_path,
                    mart_csv_file_path=raw_mart_file_path,
                    mart_name=mart_name,
                    company_db_info=company_db_info,
                    delimiter=delimiter,
                    encoding=enc,
                    variable_json=new_variable_json,
                    except_columns=except_columns,
                    check_all_rows_to_infer_type=check_all_rows_to_infer_type,
                )
                break
            except UnicodeDecodeError:
                # no encoding has been succeeded
                if cur_idx == len(supported_enc_types) - 1:
                    raise Exception(
                        (
                            "The file in server may contain Hangeul or unicode character that cannot be decoded."
                            "Please convert file encoding to cp949 or utf-8 or remove Hangeul or unicode character."
                        )
                    )
            except Exception:
                raise
    try:
        company_db_info = db_utils.get_company_db_info_from_service_db_info(
            service_db_info=service_db_info, company_db_name_enc=db_name_enc
        )
        add_mart_meta(
            db_info=company_db_info,
            mart_name=mart_name,
            mart_description=mart_description,
            user_id=user_id,
            rows_cnt=rows_cnt,
            data_file_name=mart_name,
            delimiter=delimiter,
            variable_json=new_variable_json,
            domain_json=domain_json,
            svd_json=svd_json,
        )
    except Exception as e:
        # [2022-08-03] syg - there is no mart when exception is raised while adding mart meta
        if not str(e).startswith("[LengthError]"):
            delete_mart(
                service_db_info=service_db_info,
                auth_key=auth_key,
                mart_name=mart_name,
                file_server_host=file_server_host,
                file_server_port=file_server_port,
            )
        raise e
    if do_data_profile:
        try:
            calculate_statistics_uploaded_mart(
                service_db_info=service_db_info,
                file_server_host=file_server_host,
                file_server_port=file_server_port,
                result_file_path_faf=result_file_path_faf,
                done_file_path_faf=done_file_path_faf,
                root_dir=root_dir,
                features_json=new_variable_json,
                meta_json=meta_json,
            )
        except Exception as e:
            raise Exception(
                f"Mart is uploaded successfully but data-profiling failed. {str(e)}"
            )

    # write row count to the result file
    with open(result_file_path_faf, "w") as rfd, open(
        done_file_path_faf, "w"
    ) as dfd:
        rfd.write(str(rows_cnt))
        dfd.write(constants.FAF_DONE_STRING)

    finally:
        os.remove(new_mart_file_path)

def upload_mart(
    service_db_info,
    root_dir,
    result_file_path_faf,
    done_file_path_faf,
    meta_json,
    raw_mart_file_path,
    file_server_host,
    file_server_port,
    external_purpose,
):
    auth_key = meta_json["AuthKey"]
    mart_name = meta_json["MartName"]
    mart_description = meta_json["MartDescription"]
    delimiter = meta_json["Delimiter"]
    domain_json = meta_json["DomainJson"]
    svd_json = meta_json["SvdJson"]
    variable_json = meta_json["VariableJson"]
    except_columns = meta_json["ExceptColumns"]
    # fire and forget files
    client_polling_dir = os.path.join(root_dir, constants.CLIENT_POLLING_DIR_NAME)
    check_all_rows_to_infer_type = meta_json["CheckAllRowsToInferType"]
    preserve_data_integrity = meta_json["PreserveDataIntegrity"]  # [2023-08-11] sjh
    do_data_profile = meta_json["DoDataProfile"]
    has_header = meta_json["HasHeaderFirstLine"]

    company_and_user_info = db_utils.get_company_and_user_info(
        service_db_info=service_db_info, auth_key=auth_key
    )
    db_name_enc = company_and_user_info.company_db_name_enc
    company_code = company_and_user_info.company_code
    user_id = company_and_user_info.user_id
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info=service_db_info, company_db_name_enc=db_name_enc
    )

    # [2020-09-16] pjh - disable mart upload when app is for external use and user auth level is 2 or 3
    # auth_level = get_auth_level(db_info=company_db_info, user_id=user_id)
    # if external_purpose and auth_level > 1:
    #     raise Exception("Only administrator can upload mart")

    # Check raw data with or with header and add,
    # [2018-09-07] pjh - upload data except void column
    header_names = []
    new_variable_json = []
    # features_json = []
    for var_info in variable_json:
        if not has_header:
            header_names.append(var_info["VAR_NM"])
        if var_info["VAR_NM"] not in except_columns:
            new_variable_json.append(var_info)
            # features_json.append(var_info)

    if len(new_variable_json) == 0:
        raise Exception("There is no data.")

    new_mart_file_path = common_utils.make_temp_file()
    # [2019-10-29] pjh - use utf-8-sig first
    # supported_enc_types = ['cp949', 'utf-8-sig']
    supported_enc_types = ["utf-8-sig", "cp949"]
    try:
        with open(new_mart_file_path, "wb") as tmp_fd:
            # read csv -> processing(add system key, ...)
            cur_idx = 0
            rows_cnt = 0

            for cur_idx, enc in enumerate(supported_enc_types):
                # process uploaded mart(type infer, ...)
                try:
                    # [2023-08-11] sjh - 클라이언트에서 원본 데이터 유지 여부를 파라미터로 받고,
                    #                    유지하는 경우에는 기존처럼 모든 변수를 string 형태로 업로드,
                    #                    유지 안해도 되는 경우에는 variable_json 의 데이터 형식에 맞춰서 업로드.
                    if preserve_data_integrity:
                        new_variable_json, rows_cnt = process_uploaded_mart(
                            mart_csv_file_path=raw_mart_file_path,
                            new_mart_parquet_path=new_mart_file_path,
                            delimiter=delimiter,
                            encoding=enc,
                            variable_json=new_variable_json,
                            except_columns=except_columns,
                            check_all_rows_to_infer_type=check_all_rows_to_infer_type,
                            header_names=header_names,
                        )
                    else:
                        (
                            new_variable_json,
                            rows_cnt,
                        ) = process_uploaded_mart_with_variable_json(
                            mart_csv_file_path=raw_mart_file_path,
                            new_mart_parquet_path=new_mart_file_path,
                            delimiter=delimiter,
                            encoding=enc,
                            variable_json=new_variable_json,
                            except_columns=except_columns,
                            header_names=header_names,
                        )

                    break
                except UnicodeDecodeError:
                    # no encoding has been succeeded
                    if cur_idx == len(supported_enc_types) - 1:
                        raise Exception(
                            (
                                "The file in server may contain Hangeul or unicode character that cannot be decoded."
                                "Please convert file encoding to cp949 or utf-8 or remove Hangeul or unicode character."
                            )
                        )
                except Exception:
                    raise

        try:
            new_mart_file_name = data_utils.upload_file_or_bytes(
                file_server_host,
                file_server_port,
                company_code,
                new_mart_file_path,
                constants.FileTypeFlag.ML_MART,
            )

            company_db_info = db_utils.get_company_db_info_from_service_db_info(
                service_db_info=service_db_info, company_db_name_enc=db_name_enc
            )

            add_mart_meta(
                db_info=company_db_info,
                mart_name=mart_name,
                mart_description=mart_description,
                user_id=user_id,
                rows_cnt=rows_cnt,
                data_file_name=new_mart_file_name,
                delimiter=delimiter,
                variable_json=new_variable_json,
                domain_json=domain_json,
                svd_json=svd_json,
            )
        except Exception as e:
            # [2022-08-03] syg - there is no mart when exception is raised while adding mart meta
            if not str(e).startswith("[LengthError]"):
                delete_mart(
                    service_db_info=service_db_info,
                    auth_key=auth_key,
                    mart_name=mart_name,
                    file_server_host=file_server_host,
                    file_server_port=file_server_port,
                )
            raise e
        if do_data_profile:
            try:
                calculate_statistics_uploaded_mart(
                    service_db_info=service_db_info,
                    file_server_host=file_server_host,
                    file_server_port=file_server_port,
                    result_file_path_faf=result_file_path_faf,
                    done_file_path_faf=done_file_path_faf,
                    root_dir=root_dir,
                    features_json=new_variable_json,
                    meta_json=meta_json,
                )
            except Exception as e:
                raise Exception(
                    f"Mart is uploaded successfully but data-profiling failed. {str(e)}"
                )

        # write row count to the result file
        with open(result_file_path_faf, "w") as rfd, open(
            done_file_path_faf, "w"
        ) as dfd:
            rfd.write(str(rows_cnt))
            dfd.write(constants.FAF_DONE_STRING)

    finally:
        os.remove(new_mart_file_path)


def add_mart_meta(
    db_info,
    mart_name,
    mart_description,
    user_id,
    rows_cnt,
    data_file_name,
    delimiter,
    variable_json,
    domain_json,
    svd_json,
):
    add_mart_meta_queries = []
    add_mart_meta_params = []

    table_meta_insert_query = """
        INSERT INTO TB_DATA_USER_MNG (
            TABLE_ID,
            TABLE_DESC,
            USER_ID,
            ROW_COUNT,
            ORG_REG_DATE,
            LAST_SAVE_DATE,
            TABLE_FILE_NM,
            `DELIMITER`
        ) VALUES (%s, %s, %s, %s, NOW(), NOW(), %s, %s);
    """

    table_meta_insert_param = (
        mart_name,
        mart_description,
        user_id,
        rows_cnt,
        data_file_name,
        delimiter,
    )

    add_mart_meta_queries.append(table_meta_insert_query)
    add_mart_meta_params.append(table_meta_insert_param)

    # variable info
    var_meta_insert_query = """
        INSERT INTO TB_DATA_VAR_INFO(
            TABLE_ID,
            VAR_NM,
            VAR_DESC,
            VAR_FORM,
            VAR_LEN,
            VAR_SCALE,
            VAR_ROLE,
            VAR_DOMAIN,
            MIN_VALUE,
            MAX_VALUE,
            ORG_REG_DATE,
            LAST_SAVE_DATE
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
    """

    var_meta_insert_param = []

    for var_info in variable_json:
        var_len = var_info["VAR_LEN"]
        var_role = var_info["VAR_ROLE"]
        var_domain = var_info["VAR_DOMAIN"]
        var_form = var_info["VAR_FORM"]

        if var_form in [
            str(constants.VarForm.NUM_DISC.value),
            str(constants.VarForm.NUM_CONT.value),
        ]:
            var_scale = var_info["VAR_SCALE"]
            min_val = var_info["MIN_VALUE"]
            max_val = var_info["MAX_VALUE"]
        else:
            # null
            var_scale = None
            min_val = None
            max_val = None

        # [2022-02-17] ldk - save meta data of binary variable as binary not char
        if len(var_info["VAR_NM"]) > 30:
            raise Exception(
                f"[LengthError] {var_info['VAR_NM']} exceeds 30 characters."
            )
        if len(var_info["VAR_DESC"]) > 100:
            raise Exception(
                f"[LengthError] Description of {var_info['VAR_NM']} exceeds 100 characters."
            )

        var_meta_insert_param.append(
            (
                mart_name,
                var_info["VAR_NM"],
                var_info["VAR_DESC"],
                var_form,
                var_info["VAR_LEN"],
                var_scale,
                var_info["VAR_ROLE"],
                var_info["VAR_DOMAIN"],
                min_val,
                max_val,
            )
        )

    add_mart_meta_queries.append(var_meta_insert_query)
    add_mart_meta_params.append(var_meta_insert_param)

    # domain info
    domain_meta_insert_query = """
        INSERT INTO
            TB_VAR_DOMAIN_MNG(TABLE_ID, DOMAIN_INDEX, DOMAIN_NM, LAST_SAVE_DATE)
        VALUES
            (%s, %s, %s, NOW())
    """

    domain_meta_insert_param = []

    for domain_info in domain_json:
        # [2022-11-29] ldk - add domain name length exception message.
        if len(domain_info["DOMAIN_NM"]) > 50:
            raise Exception(
                f"[LengthError] Domain Index '{domain_info['DOMAIN_INDEX']}' exceeds 50 characters."
            )

        domain_meta_insert_param.append(
            (mart_name, domain_info["DOMAIN_INDEX"], domain_info["DOMAIN_NM"])
        )

    add_mart_meta_queries.append(domain_meta_insert_query)
    add_mart_meta_params.append(domain_meta_insert_param)

    # svd_meta_insert_query = '''
    #     INSERT INTO
    #         TB_DATA_SVD(TABLE_ID, SVD_DOMAIN, SVD_VALUE, SVD_LBL, LAST_SAVE_DATE)
    #     VALUES
    #         (%s, %s, %s, %s, NOW());
    # '''

    # [2023-04-05] N-Builder New query.
    svd_meta_insert_query = """
        INSERT INTO
            TB_DATA_VAR_SVD(TABLE_ID, VAR_NM, SVD_VALUE, SVD_NM, SVD_LBL, LAST_SAVE_DATE)
        VALUES
            (%s, %s, %s, %s, %s, NOW());
    """

    svd_meta_insert_param = []
    # svd info
    for svd_info in svd_json:
        svd_meta_insert_param.append(
            (
                mart_name,
                svd_info["VAR_NM"],
                svd_info["SVD_VALUE"],
                svd_info["SVD_NM"],
                svd_info["SVD_LBL"],
            )
        )

    add_mart_meta_queries.append(svd_meta_insert_query)
    add_mart_meta_params.append(svd_meta_insert_param)

    db_utils.execute_modify_query(
        db_info=db_info, query=add_mart_meta_queries, param=add_mart_meta_params
    )


def calculate_statistics_uploaded_mart(
    service_db_info,
    file_server_host,
    file_server_port,
    result_file_path_faf,
    done_file_path_faf,
    root_dir,
    features_json,
    meta_json,
):
    auth_key = meta_json["AuthKey"]
    mart_name = meta_json["MartName"]

    company_and_user_info = db_utils.get_company_and_user_info(
        service_db_info, auth_key
    )

    company_code = company_and_user_info.company_code
    company_db_name_enc = company_and_user_info.company_db_name_enc
    user_id = company_and_user_info.user_id
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    # Casel. Mart(Data Management)
    profiling_result_json = data_utils.variable_profiling(
        service_db_info,
        file_server_host,
        file_server_port,
        result_file_path_faf,
        done_file_path_faf,
        root_dir,
        auth_key,
        mart_name,
        features_json,
    )

    # Upload profiling result json
    temp_file_path = common_utils.make_temp_file()
    # common_utils.dump_json_to_file(profiling_result_json, temp_file_path)

    profiling_result_str = json.dumps(profiling_result_json)
    profiling_result_str_enc = crypto_utils.encrypt_with_key(
        profiling_result_str, crypto_key="DataProfilingEncryption"
    )

    with open(temp_file_path, "w") as f:
        f.write(profiling_result_str_enc)

    data_profiling_file_name = data_utils.upload_file_or_bytes(
        file_server_host,
        file_server_port,
        company_code,
        temp_file_path,
        constants.FileTypeFlag.ML_MART,
    )

    os.remove(temp_file_path)

    update_stg_query = """
        UPDATE TB_DATA_USER_MNG
            SET PROFILING_FILE_NM = %s
        WHERE TABLE_ID = %s
    """
    # Update Profiling Result Filename
    db_utils.execute_modify_query(
        db_info=company_db_info,
        query=update_stg_query,
        param=(data_profiling_file_name, mart_name),
    )

    with open(result_file_path_faf, "w") as rfd, open(done_file_path_faf, "w") as dfd:
        rfd.write(data_profiling_file_name)
        dfd.write(constants.FAF_DONE_STRING)


def delete_mart(
    service_db_info, auth_key, mart_name, file_server_host, file_server_port
):
    company_and_user_info = db_utils.get_company_and_user_info(
        service_db_info=service_db_info, auth_key=auth_key
    )
    db_name_enc = company_and_user_info.company_db_name_enc
    user_id = company_and_user_info.user_id
    company_code = company_and_user_info.company_code

    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info=service_db_info, company_db_name_enc=db_name_enc
    )

    mart_info = data_utils.ml_get_mart_info(
        company_db_info=company_db_info, mart_name=mart_name
    )
    mart_file_name = mart_info.mart_file_name

    delete_mart_queries, delete_mart_params = [], []
    delete_user_mng_query = """
        DELETE FROM
            TB_DATA_USER_MNG
        WHERE
            TABLE_ID = %s
    """
    delete_mart_queries.append(delete_user_mng_query)
    delete_mart_params.append((mart_name,))

    delete_var_info_query = """
        DELETE FROM
            TB_DATA_VAR_INFO
        WHERE
            TABLE_ID = %s
    """
    delete_mart_queries.append(delete_var_info_query)
    delete_mart_params.append((mart_name,))

    # change from TB_DATA_SVD to TB_DATA_VAR_SVD
    delete_svd_query = """
        DELETE FROM
            TB_DATA_VAR_SVD
        WHERE
            TABLE_ID = %s
    """
    delete_mart_queries.append(delete_svd_query)
    delete_mart_params.append((mart_name,))

    delete_domain_mng_query = """
        DELETE FROM
            TB_VAR_DOMAIN_MNG
        WHERE
            TABLE_ID = %s
    """
    delete_mart_queries.append(delete_domain_mng_query)
    delete_mart_params.append((mart_name,))

    # [2023-01-11] ldk - check local Windows version and delete table from db.
    is_mart_from_db = (
        int(common_utils.get_config_by_key("CUSTOM", "MART_DATA_UPLOAD_TYPE"))
        == constants.MartUploadType.DB.value
    )
    if is_mart_from_db:
        drop_windows_table_query = """
            DROP TABLE IF EXISTS `{0}`
        """.format(
            mart_name
        )
        delete_mart_queries.append(drop_windows_table_query)
        delete_mart_params.append(())

    db_utils.execute_modify_query(
        db_info=company_db_info, query=delete_mart_queries, param=delete_mart_params
    )

    # delete mart file
    if not is_mart_from_db:
        data_utils.delete_file(
            file_server_host,
            file_server_port,
            company_code,
            mart_file_name,
            constants.FileTypeFlag.ML_MART,
        )

    # [2021-11-16] sjh - delete profiling file
    try:
        data_utils.delete_file(
            file_server_host,
            file_server_port,
            company_code,
            mart_info.profiling_file_name,
            constants.FileTypeFlag.ML_MART,
        )
    except:
        pass


def process_uploaded_mart(
    mart_csv_file_path,
    new_mart_parquet_path,
    delimiter,
    encoding,
    variable_json,
    except_columns: list[Any] = [],
    check_all_rows_to_infer_type: bool = False,
    header_names: list[Any] = [],
):
    # [2020-01-28] pjh - because of high memory usage, we iterate by chunk
    chunk_size = 50000
    pq_writer = None
    col_type_dict, col_is_numeric_dict = {}, {}
    data_len = 0
    # [2020-04-03] pjh - add table schema (each table schema can be different during iteration)
    table_schema = None
    # [2023-01-19] ldk - add csv upload mode.
    mart_data_upload_type = common_utils.get_config_by_key(
        "CUSTOM", "MART_DATA_UPLOAD_TYPE"
    )
    is_mart_csv = int(mart_data_upload_type) == constants.MartUploadType.CSV.value

    compression = "gzip" if mart_csv_file_path.endswith(".gz") else "infer"
    if len(header_names) > 0:
        chunk_dfs = enumerate(
            pd.read_csv(
                mart_csv_file_path,
                sep=delimiter,
                index_col=False,
                dtype="object",
                encoding=encoding,
                chunksize=chunk_size,
                names=header_names,
                compression=compression,
            )
        )
    else:
        chunk_dfs = enumerate(
            pd.read_csv(
                mart_csv_file_path,
                sep=delimiter,
                index_col=False,
                dtype="object",
                encoding=encoding,
                chunksize=chunk_size,
            )
        )

    for i, df in chunk_dfs:
        # drop except columns
        if len(except_columns) > 0:
            df.drop(except_columns, axis=1, inplace=True)
        data_len += len(df)
        df.loc[:, constants.DATA_KEY] = pd.Series(
            np.arange(
                1 * chunk_size + 1, 1 * chunk_size + min(len(df), chunk_size) + 1
            ),
            index=df.index,
        ).astype(np.uint32)

        if check_all_rows_to_infer_type:
            for col_name in df.columns:
                if col_name != constants.DATA_KEY:
                    # [2020-04-28] pjh - str.isnumeric() has some fault
                    can_convert_to_numeric = True
                    try:
                        df[col_name].astype(float)
                    except ValueError:
                        can_convert_to_numeric = False

                    col_is_numeric_dict[col_name] = (
                        col_is_numeric_dict.get(col_name, True)
                        and can_convert_to_numeric
                    )
                    if col_is_numeric_dict[col_name]:
                        col_type_dict[col_name] = str(constants.VarForm.NUM_CONT.value)
                    else:
                        col_type_dict[col_name] = str(constants.VarForm.CHAR.value)
        else:
            # [2021-06-21] sjh - check the values if variable form is numeric type.
            # Notify the variable name and error values.
            for var_info in variable_json:
                if var_info["VAR_FORM"] in [
                    str(constants.VarForm.NUM_CONT.value),
                    str(constants.VarForm.NUM_DISC.value),
                    str(constants.VarForm.NUM_BINARY.value),
                ]:
                    col_name = var_info["VAR_NM"]
                    try:
                        df[col_name].astype(float)
                    except ValueError as e:
                        raise Exception(f"{col_name} " + str(e))

        # csv upload,
        if is_mart_csv:
            # csv file in new_mart_parquet_path
            if i == 0:
                df.to_csv(
                    new_mart_parquet_path, index=False, mode="w", encoding="utf-8"
                )
            else:
                df.to_csv(
                    new_mart_parquet_path,
                    header=False,
                    index=False,
                    mode="a",
                    encoding="utf-8",
                )
        # parquet upload,
        else:
            # [2020-04-03] pjh - use predefined schema(uint32, string)
            if i == 0:
                table_schema = pyarrow.schema(
                    [pyarrow.field(constants.DATA_KEY, pyarrow.uint32())]
                    + [
                        pyarrow.field(col, pyarrow.string())
                        for col in df.columns
                        if col != constants.DATA_KEY
                    ]
                )
                pq_writer = pq.ParquetWriter(new_mart_parquet_path, table_schema)

            table = pyarrow.Table.from_pandas(
                df, schema=table_schema, preserve_index=False
            )
            pq_writer.write_table(table)

    if not is_mart_csv and pq_writer:
        pq_writer.close()

    # add system key
    # df.loc[:, constants.DATA_KEY] = pd.Series(np.arange(1, len(df) + 1), index=df.index)
    # [2020-01-28] pjh - uint64 -> uint32
    # df[constants.DATA_KEY] = df[constants.DATA_KEY].astype(np.uint32)
    # df.to_parquet(fname=new_mart_parquet_path, engine='pyarrow', index=False)

    # if check_all_rows_to_infer_type:
    #     col_type_dict = {}
    #     for col_name in df.columns:
    #         if col_name != constants.DATA_KEY:
    #             if df[col_name].str.isnumeric().all():
    #                 col_type_dict[col_name] = str(constants.VarForm.NUM_CONT.value)
    #             else:
    #                 col_type_dict[col_name] = str(constants.VarForm.CHAR.value)

    if check_all_rows_to_infer_type:
        for var_info in variable_json:
            assert var_info["VAR_NM"] in col_type_dict
            var_info["VAR_FORM"] = col_type_dict[var_info["VAR_NM"]]

    return variable_json, data_len


# [2023-01-04] process uploaded mart local windows platform.
def process_uploaded_mart_to_db(
    mart_csv_file_path,
    mart_name,
    company_db_info,
    delimiter,
    encoding,
    variable_json,
    except_columns: list[Any] = [],
    check_all_rows_to_infer_type: bool = False,
):
    primary_key_list = [
        "`{0}` INT UNSIGNED NOT NULL, PRIMARY KEY (`{0}`)".format(
            constants.DATA_KEY
        )
    ]
    col_list_query = ", ".join(col_list + primary_key_list)

    # DROP if table exists
    drop_mart_data_db_query = """
        DROP TABLE IF EXISTS `{0}`
    """.format(
        mart_name
    )
    save_mart_data_queries.append(drop_mart_data_db_query)
    save_mart_data_params.append(())

    create_mart_data_db_query = """
        CREATE TABLE `{0}` ({1})
    """.format(
        *args: mart_name, col_list_query
    )
    save_mart_data_queries.append(create_mart_data_db_query)
    save_mart_data_params.append(())

    # db_utils.execute_modify_query(
    #     db_info=company_db_info,
    #     query=[drop_mart_data_db_query, create_mart_data_db_query],
    # )

    insert_mart_data_db_query = """
        INSERT INTO `{0}` ({1})
        VALUES ({2})
    """.format(
        *args: mart_name, insert_query_column_names, insert_query_placeholders
    )
    insert_mart_data_db_param = []
    # change nan to None to insert to mysql.
    df = df.where(pd.notnull(df), None)
    for idx, row in df.iterrows():
        insert_mart_data_db_param.append(tuple(row))
   

        save_mart_data_queries.append(insert_mart_data_db_query)
        save_mart_data_params.append(insert_mart_data_db_param)

    db_utils.execute_modify_query(
        db_info=company_db_info,
        query=save_mart_data_queries,
        param=save_mart_data_params,
    )

    if check_all_rows_to_infer_type:
        for var_info in variable_json:
            assert var_info["VAR_NM"] in col_type_dict
            var_info["VAR_FORM"] = col_type_dict[var_info["VAR_NM"]]

    return variable_json, data_len


def process_uploaded_mart_with_variable_json(
    mart_csv_file_path,
    new_mart_parquet_path,
    delimiter,
    encoding,
    variable_json,
    except_columns: list[Any] = [],
    header_names: list[Any] = [],
):
    print("numeric upload")

    chunk_size = 50000
    data_len = 0
    pq_writer = None
    table_schema = None

    compression = "gzip" if mart_csv_file_path.endswith(".gz") else "infer"
    if len(header_names) > 0:
        columns = pd.read_csv(
            mart_csv_file_path,
            sep=delimiter,
            index_col=False,
            dtype="object",
            names=header_names,
            nrows=5,
            compression=compression,
        ).columns.to_list()
    else:
        columns = pd.read_csv(
            mart_csv_file_path,
            sep=delimiter,
            index_col=False,
            dtype="object",
            nrows=5,
            compression=compression,
        ).columns.to_list()
    for col in except_columns:
        columns.remove(col)

    # define dtype
    dtype_pandas, dtype_pyarrow = get_dtype_from_variable_json(variable_json, columns)
    # dtype_pandas = {}
    # dtype_pyarrow = []
    # for var_info in variable_json:
    #     var_nm = var_info['VAR_NM']
    #     if var_nm in columns:
    #         # Numeric - Discrete as object
    #         if var_info['VAR_FORM'] == str(constants.VarForm.NUM_CONT.value):
    #             dtype_pandas[var_info['VAR_NM']] = np.float64
    #             dtype_pyarrow.append(pyarrow.field(var_nm, pyarrow.float64()))
    #         elif var_info['VAR_FORM'] == str(constants.VarForm.NUM_BINARY.value):
    #             dtype_pandas[var_info['VAR_NM']] = np.float32
    #             dtype_pyarrow.append(pyarrow.field(var_nm, pyarrow.float32()))
    #         else:
    #             dtype_pandas[var_info['VAR_NM']] = 'object'
    #             dtype_pyarrow.append(pyarrow.field(var_nm, pyarrow.string()))

    assert len(columns) == len(dtype_pandas)

    if len(header_names) > 0:
        chuck_dfs = enumerate(
            pd.read_csv(
                mart_csv_file_path,
                sep=delimiter,
                index_col=False,
                dtype=dtype_pandas,
                encoding=encoding,
                chunksize=chunk_size,
                names=header_names,
                usecols=columns,
                compression=compression,
            )
        )
    else:
        chuck_dfs = enumerate(
            pd.read_csv(
                mart_csv_file_path,
                sep=delimiter,
                index_col=False,
                dtype=dtype_pandas,
                encoding=encoding,
                chunksize=chunk_size,
                usecols=columns,
                compression=compression,
            )
        )

    for i, df in chuck_dfs:
        data_len += len(df)
        df[constants.DATA_KEY] = pd.Series(
            np.arange(
                i * chunk_size + 1, i * chunk_size + min(len(df), chunk_size) + 1
            ),
            index=df.index,
        ).astype(np.uint32)

        if i == 0:
            table_schema = pyarrow.schema(
                [pyarrow.field(constants.DATA_KEY, pyarrow.uint32())] + dtype_pyarrow
            )
            pq_writer = pq.ParquetWriter(new_mart_parquet_path, table_schema)

        table = pyarrow.Table.from_pandas(df, schema=table_schema, preserve_index=False)
        pq_writer.write_table(table)

    pq_writer.close()

    return variable_json, data_len


def get_dtype_from_variable_json(variable_json, columns=None):
    dtype_pandas = {}
    dtype_pyarrow = []

    for var_info in variable_json:
        var_nm = var_info["VAR_NM"]
        if columns is None or var_nm in columns:
            if var_nm == constants.DATA_KEY:
                dtype_pandas[var_nm] = np.uint32
                dtype_pyarrow.append(pyarrow.field(var_nm, pyarrow.uint32()))
            elif var_info["VAR_FORM"] == str(constants.VarForm.NUM_CONT.value):
                dtype_pandas[var_nm] = np.float64
                dtype_pyarrow.append(pyarrow.field(var_nm, pyarrow.float64()))
            elif var_info["VAR_FORM"] == str(constants.VarForm.NUM_BINARY.value):
                dtype_pandas[var_nm] = np.float32
                dtype_pyarrow.append(pyarrow.field(var_nm, pyarrow.float32()))
            else:
                dtype_pandas[var_nm] = "object"
                dtype_pyarrow.append(pyarrow.field(var_nm, pyarrow.string()))

    return dtype_pandas, dtype_pyarrow


def get_mart_columns(
    service_db_info,
    file_server_host,
    file_server_port,
    company_code,
    mart_name,
    flow_id,
    include_var_info: bool = False,
):
    company_db_name_enc = db_utils.get_company_db_name_enc(
        service_db_info, company_code
    )
    company_db_info = db_utils.get_company_db_info_from_service_db_info(
        service_db_info, company_db_name_enc
    )

    select_mart_columns_query = """
        SELECT COL_NAME AS VAR_NM, IS_PERF_COL
        FROM TB_SV_DATA_COLUMNS
        WHERE TABLE_ID = %s
        ORDER BY IS_PERF_COL DESC, COL_NAME
    """

    mart_columns_json = db_utils.execute_select_query(
        company_db_info, select_mart_columns_query, param=(mart_name,)
    )
    if len(mart_columns_json) == 0:
        raise Exception("No such mart!")

    if flow_id > 0:
        select_flow_target_columns_query = """
            SELECT COL_NAME AS VAR_NM, IS_PERF_COL
            FROM TB_SV_FLOW_COLUMNS
            WHERE FLOW_ID = %s AND IS_PERF_COL = 1
        """

        select_flow_target_columns_json = db_utils.execute_select_query(
            company_db_info, select_flow_target_columns_query, param=(flow_id,)
        )

        if include_var_info:
            select_prod_var_info_query = """
                SELECT VAR_NM, VAR_DESC, VAR_FORM, MINING_ROLE
                FROM TB_SV_PRODUCT_VAR_INFO
                WHERE PRODUCT_ID = (SELECT PRODUCT_ID FROM TB_SV_FLOW WHERE FLOW_ID = %s)
            """
            var_info_json = db_utils.execute_select_query(
                company_db_info, select_prod_var_info_query, param=(flow_id,)
            )
            if len(var_info_json) == 0:
                select_model_layout_file_query = """
                    SELECT
                        flow_model_mng.MODEL_ID, model.LAYOUT_FILE_NAME
                    FROM
                        TB_SV_FLOW flow
                    LEFT JOIN
                        TB_SV_FLOW_MODEL_MNG flow_model_mng
                        ON flow.FLOW_HISTORY_ID = flow_model_mng.FLOW_HISTORY_ID
                    LEFT JOIN
                        TB_SV_MODEL model
                        ON flow_model_mng.MODEL_ID = model.MODEL_ID
                    WHERE flow_model_mng.FLOW_ID = %s;
                """

                model_layout_file_json = db_utils.execute_select_query(
                    company_db_info, select_model_layout_file_query, param=(flow_id,)
                )
                layout_df = pd.DataFrame(
                    columns=["VAR_NM", "VAR_DESC", "VAR_FORM", "MINING_ROLE", "CC_USE"]
                )
                for model_layout_file in model_layout_file_json:
                    layout_file_url = data_utils.get_file_url(
                        file_server_host,
                        file_server_port,
                        company_code,
                        model_layout_file["LAYOUT_FILE_NAME"],
                        constants.FileTypeFlag.SERVING_MODEL,
                    )
                    model_layout_df = pd.read_csv(
                        layout_file_url,
                        index_col=False,
                        header=None,
                        names=layout_df.columns,
                    )
                    layout_df = pd.concat([layout_df, model_layout_df]).reset_index(
                        drop=True
                    )
                layout_df = layout_df.drop_duplicates(["VAR_NM"], keep="first")

                def _convert_column(convert_key, convert_dict):
                    try:
                        return str(convert_dict[convert_key].value)
                    except:
                        return None

                layout_df["VAR_FORM"] = layout_df["VAR_FORM"].apply(
                    lambda x: _convert_column(x, constants.VAR_FORM_STR_TO_VAR_FORM)
                )
                layout_df["MINING_ROLE"] = layout_df["MINING_ROLE"].apply(
                    lambda x: _convert_column(
                        x, constants.MINING_ROLE_STR_TO_MINING_ROLE
                    )
                )

                mart_columns_df = pd.merge(
                    left=pd.DataFrame(mart_columns_json),
                    right=layout_df,
                    how="left",
                    on="VAR_NM",
                )

                init_var_info_df = mart_columns_df[mart_columns_df["VAR_FORM"].isna()]
                if init_var_info_df.shape[0] > 0:
                    set_product_id_query = """
                        SET @PRODUCT_ID = (SELECT PRODUCT_ID FROM TB_SV_FLOW WHERE FLOW_ID = %s);
                    """
                    insert_prod_var_info_query = """
                        INSERT INTO TB_SV_PRODUCT_VAR_INFO (PRODUCT_ID, VAR_NM, VAR_DESC, VAR_FORM, MINING_ROLE)
                        VALUES (@PRODUCT_ID, %s, %s, %s, %s);
                    """
                    insert_prod_var_info_params = [
                        (
                            row["VAR_NM"],
                            row["VAR_DESC"],
                            row["VAR_FORM"],
                            row["MINING_ROLE"],
                        )
                        for _, row in init_var_info_df.iterrows()
                    ]
                    db_utils.execute_modify_query(
                        db_info=company_db_info,
                        query=[set_product_id_query, insert_prod_var_info_query],
                        param=[(flow_id,), insert_prod_var_info_params],
                    )
            else:
                mart_columns_df = pd.merge(
                    left=pd.DataFrame(mart_columns_json),
                    right=pd.DataFrame(var_info_json),
                    how="left",
                    on="VAR_NM",
                )

            mart_columns_df["VAR_DESC"] = mart_columns_df["VAR_DESC"].fillna("")
            mart_columns_df["VAR_FORM"] = mart_columns_df["VAR_FORM"].fillna(
                str(constants.VarForm.VOID.value)
            )
            mart_columns_df["MINING_ROLE"] = mart_columns_df["MINING_ROLE"].fillna(
                str(constants.MiningRole.NONE.value)
            )

            mart_columns_json = json.loads(
                mart_columns_df.to_json(orient="records", force_ascii=False)
            )

        flow_target_columns_name = [
            col["VAR_NM"] for col in select_flow_target_columns_json
        ]

        mart_flow_columns_json = []
        for col in mart_columns_json:
            if col["VAR_NM"] in flow_target_columns_name:
                col["IS_PERF_COL"] = 1
                mart_flow_columns_json.append(col)
        for col in mart_columns_json:
            if col["VAR_NM"] not in flow_target_columns_name:
                mart_flow_columns_json.append(col)
        return mart_flow_columns_json

    return mart_columns_json


