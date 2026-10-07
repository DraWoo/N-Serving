#!/bin/bash

# sleep for 5 seconds (intentional delay)
sleep 5

set -e
# check required environment variables
# [2020-11-06] pjh - add CHIPS_UPLOAD_ENABLED
# [2020-11-11] pjh - add CHIPS_USE_SHINHAN_CARD_DW
OLD_IFS=$IFS

# [2021-03-25] pjh - read from environment list file
while IFS= read -r line; do
    ENV_VAR=$(echo $line | cut -d'=' -f1)
    if [ -z "${!ENV_VAR}" ]; then
        echo "Environment variable ${ENV_VAR} is missing"; exit 1
    fi
done </env/serving-backend-env.list

IFS=$OLD_IFS

# nginx conf (access / ssl)
envsubst '$0000 $NGINX_SERVER_NAME $NGINX_SSL_ON_OFF' < "/config/nginx/nginx.conf.template" > "/python_modules/nice_serving_backend/nginx.conf"


# [2022-10-26] syg - use base image h2o if H2O_VERSION_INDEX=-1, else install h2o from mounted path /h2o-setup
# [2022-03-07] syg - python h2o install
if [ "$H2O_VERSION_INDEX" = "0" ]; then
    python -m pip install /h2o-setup/h2o-3.16.0.3-py2.py3-none-any.whl
elif [ "$H2O_VERSION_INDEX" = "1" ]; then
    python -m pip install /h2o-setup/h2o-3.18.0.2-py2.py3-none-any.whl
elif [ "$H2O_VERSION_INDEX" = "2" ]; then
    python -m pip install /h2o-setup/h2o-3.36.0.1-py2.py3-none-any.whl
elif [ "$H2O_VERSION_INDEX" = "3" ]; then
    python -m pip install /h2o-setup/h2o-3.36.1.2-py2.py3-none-any.whl
fi


# replace python config file
export MARIADB_PW_ENC=$(python -c "from nice_serving_backend.utils import crypto_utils; print(crypto_utils.encrypt('${MARIADB_PW}'))")
export SERVICE_DB_NAME_ENC=$(python -c "from nice_serving_backend.utils import crypto_utils; print(crypto_utils.encrypt('${SERVICE_DB_NAME}'))")
export OPER_MARIADB_PW_ENC=$(python -c "from nice_serving_backend.utils import crypto_utils; print(crypto_utils.encrypt('${OPER_MARIADB_PW}'))")
export OPER_SERVICE_DB_NAME_ENC=$(python -c "from nice_serving_backend.utils import crypto_utils; print(crypto_utils.encrypt('${OPER_SERVICE_DB_NAME}'))")
export CHIPS_UPLOAD_ODBC_URL_ENC=$(python -c "from nice_serving_backend.utils import crypto_utils; print(crypto_utils.encrypt('${CHIPS_UPLOAD_ODBC_URL}'))")
envsubst < "/config/config.ini.template" > "/python_modules/nice_serving_backend/task_server/config.ini"

# [2021-07-13] syg - add cronjob with env
#echo -e "SHELL=/bin/bash\nPYTHONPATH=${PYTHONPATH}\nLD_LIBRARY_PATH=${LD_LIBRARY_PATH}\n00 23 * * * ${PYTHON_ROOT_DIR}/bin/python /python_modules/service/etl-backoff
# echo "00 23 * * * PYTHONPATH=${PYTHONPATH}; ${PYTHON_ROOT_DIR}/bin/python /python_modules/service/etl-backoffice/task_manager.py >> /cron.log 2>&1" | crontab -
#service cron restart

/usr/bin/supervisord
