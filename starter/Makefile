# 经营看板 + 问答服务
# 换数据或知识库：make rebuild DATA_DIR=/path/data KB_DIR=/path/kb
#
# Windows 上没有 make 也能跑，等价命令写在根目录 README.md 里。

PY ?= .venv/bin/python
PORT ?= 8000
export DATA_DIR KB_DIR VAR_DIR LLM_BASE_URL LLM_API_KEY LLM_MODEL

.PHONY: setup rebuild run test web web-dev clean

setup:          ## 建虚拟环境并装依赖
	uv venv --python 3.12
	uv pip install --python $(PY) -r requirements.txt

rebuild:        ## 从 DATA_DIR 与 KB_DIR 重建清洗表和检索索引
	$(PY) -m kbqa.rebuild

run:            ## 启动服务（同时托管看板页面），默认 8000 端口
	$(PY) -m uvicorn kbqa.server:app --host 127.0.0.1 --port $(PORT)

test:           ## 跑测试
	$(PY) -m pytest tests -q

web:            ## 构建看板前端到 web/dist（产物已提交，改了前端才需要重跑）
	cd ../web && npm install && npm run build

web-dev:        ## 前端热更新开发模式，接口代理到 8000
	cd ../web && npm run dev

clean:          ## 删掉清洗表
	rm -rf var
