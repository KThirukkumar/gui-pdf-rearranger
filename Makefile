.PHONY: run venv install

run:
	@chmod +x "$(CURDIR)/run.sh"
	@"$(CURDIR)/run.sh"

venv:
	@python3 -m venv .venv
	@. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

install: venv
