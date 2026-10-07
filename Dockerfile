# ARG_SERVER_USER_TYPE
# - super (ARG_SERVER_USER_NAME: root, ARG_SERVER_USER_ID = 0)
# - service (ARG_SERVER_USER_NAME: appuser, ARG_SERVER_USER_ID = 501)

# ARG_WITH_NGINX
# - 0 (run short, long, polling)
# - 1 (run short, long, polling, nginx)

# !!! Please use non-root & without-nginx for New Installation !!!
# non-root & without-nginx: base-image-0 > service-image > final-image
# non-root & with-nginx:    base-image-1 > service-image > final-image
# root & without-nginx:     base-image-0 > super-image > final-image
# root & with-nginx:        base-image-1 > super-image > final-image

# [2026-03-18] serving은 non-root & without-nginx로 진행하되, 기존 내용은 일단 유지.

ARG ARG_SERVER_USER_TYPE
ARG ARG_WITH_NGINX


FROM nice/serving-init-3.11.9:latest AS init-image
ARG ARG_SERVER_USER_NAME
ARG ARG_SERVER_USER_ID
ARG ARG_SERVER_USER_TYPE
RUN test -n "$ARG_SERVER_USER_NAME" \
 && test -n "$ARG_SERVER_USER_ID" \
 && test -n "$ARG_SERVER_USER_TYPE"
RUN printf "[global]\n\
index=https://nx.niceinfo.co.kr/repository/pypi-group\n\
index-url=https://nx.niceinfo.co.kr/repository/pypi-group/simple\n\
trusted-host=nx.niceinfo.co.kr\n\
timeout=1000" > /etc/pip.conf
COPY setup/requirements.txt /requirements.txt
RUN python -m pip install --user --no-cache-dir --no-build-isolation -r /requirements.txt


FROM nice/serving-base-3.11.9:latest AS base-image-0
EXPOSE 12345 12346
COPY setup/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN mkdir -p /var/log/supervisord


FROM base-image-${ARG_WITH_NGINX} AS super-image
ENV PYTHON_ROOT_DIR="root/.local"


FROM base-image-${ARG_WITH_NGINX} AS service-image
ARG ARG_SERVER_USER_ID
ARG ARG_SERVER_USER_NAME
# add user/group with same uid and create home directory
# # if ARG_SERVER_USER_ID is 0 and ARG_SERVER_USER_NAME is root, run || true
RUN groupadd -g $ARG_SERVER_USER_ID$ARG_SERVER_USER_NAME \
 && useradd -r -u $ARG_SERVER_USER_ID -g $ARG_SERVER_USER_NAME$ARG_SERVER_USER_NAME \
 && mkdir -p /home/$ARG_SERVER_USER_NAME/supervisor/logs \
 && chown -R $ARG_SERVER_USER_NAME:$ARG_SERVER_USER_NAME /home/$ARG_SERVER_USER_NAME \
 || true
ENV PYTHON_ROOT_DIR="/home/$ARG_SERVER_USER_NAME/.local"
# chagne supervisor pid, log path
RUN sed -i "4i pidfile = /home/$ARG_SERVER_USER_NAME/supervisor/supervisord.pid\n\
logfile = /home/$ARG_SERVER_USER_NAME/supervisor/logs/supervisord.log\n\
\n[unix_http_server]\n\
file = /home/$ARG_SERVER_USER_NAME/supervisor/supervisor.sock\n\
\n[supervisorctl]\n\
serverurl = unix:///home/$ARG_SERVER_USER_NAME/supervisor/supervisor.sock" /etc/supervisor/conf.d/supervisord.conf
RUN chown -R $ARG_SERVER_USER_NAME:$ARG_SERVER_USER_NAME /etc/supervisor || true
# chown nginx
RUN chown -R $ARG_SERVER_USER_NAME:$ARG_SERVER_USER_NAME /nginx || true


FROM ${ARG_SERVER_USER_TYPE}-image AS final-image
ARG ARG_HOST_SETUP_FILE_NAME_IN_CONTEXT_ROOT
ARG ARG_APP_UPDATE_DIR
ARG ARG_SERVER_USER_NAME
ENV ROOT_DIR="/data/NICE/SERVING" \
    JAVA_HOME="/usr/lib/jvm/zulu-8-amd64" \
    PATH="$PATH:$PYTHON_ROOT_DIR/bin" \
    PYTHONPATH="/python_modules" \
    APP_UPDATE_DIR="$ARG_APP_UPDATE_DIR" \
    SERVER_REPOSITORY_DIR="/data/NICE/SERVING/ServerRepository" \
    MARIADB_HOST="nice-sv-db" \
    MARIADB_PORT="60002" \
    SERVICE_DB_NAME="CreOnManagerService" \
    FILE_SERVER_HOST="nice-sv-file" \
    FILE_SERVER_PORT="60003" \
    H2O_CLUSTER_SERVICE_HOST="nice-sv-h2o" \
    H2O_FILE_SERVER_PORT="60004" \
    H2O_SERVER1_PORT="54325" \
    H2O_SERVER2_PORT="54327" \
    H2O_SERVER3_PORT="54329" \
    H2O_OLDER_VERSION_PORT="54333" \
    SERVING_H2O_SERVER_PORT="54331" \
    AUTH_SERVER_HOST="nice-sv-auth" \
    AUTH_SERVER_PORT="8180" \
    MIN_IP_CHECK_LEVEL="3" \
    POSSIBLE_NEW_USER_LEVELS="1,2,3" \
    DISABLE_IP_INITIALIZE="F" \
    NUM_UNICORN_WORKERS="4" \
    OPER_MARIADB_USER="root" \
    H2O_VERSION_INDEX="-1" \
    ML_PY_NUM_THREADS="1"
COPY --from=init-image --chown=$ARG_SERVER_USER_NAME:$ARG_SERVER_USER_NAME /root/.local ${PYTHON_ROOT_DIR}
RUN mkdir -p /data/NICE/SERVING && chown -R $ARG_SERVER_USER_NAME:$ARG_SERVER_USER_NAME /data \
 && mkdir /python_modules && chown $ARG_SERVER_USER_NAME:$ARG_SERVER_USER_NAME /python_modules
COPY --chown=$ARG_SERVER_USER_NAME
