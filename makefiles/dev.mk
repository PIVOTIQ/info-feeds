##########################
### Development Tools  ###
##########################

.PHONY: dev_format
dev_format: ## Format Python code
	$(call check_venv)
	$(call print_info_section,Formatting Python code)
	$(Q)black .
	$(Q)isort .
	$(call print_success,Code formatted)

.PHONY: dev_test_feed
dev_test_feed: ## Run the test_feed.py script
	$(call check_venv)
	$(call print_info,Running test_feed.py)
	$(Q)python feed_generators/test_feed.py
	$(call print_success,Test feed completed)

.PHONY: dev_test
dev_test: ## Run the tests
	$(call check_venv)
	$(call print_info,Running tests)
	$(Q)pytest
	$(call print_success,Tests passed)

.PHONY: dev_lint
dev_lint: ## Lint Python code with ruff
	$(call check_venv)
	$(call print_info,Linting Python code)
	$(Q)ruff check .
	$(call print_success,Lint passed)
