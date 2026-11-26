##########################
### Environment Setup  ###
##########################

.PHONY: env_create
env_create: ## Create the virtual environment
	$(call print_info_section,Creating virtual environment)
	$(Q)uv venv
	$(call print_success,Virtual environment created at .venv)

.PHONY: env_source
env_source: ## Source the env; must be executed like: $$(make env_source)
	@echo 'source .venv/bin/activate'

.PHONY: env_install
env_install: ## Install dependencies using uv
	$(call print_info_section,Installing dependencies)
	$(Q)uv venv
	$(Q)uv pip install -r requirements-dev.txt
	$(call print_success,Dependencies installed)

.PHONY: clean_env
clean_env: ## Clean virtual environment
	$(call print_warning,Removing virtual environment)
	$(Q)rm -rf venv .venv
	$(call print_success,Virtual environment removed)
