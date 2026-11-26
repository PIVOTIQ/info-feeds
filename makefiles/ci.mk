##########################
### CI/CD Workflows    ###
##########################

.PHONY: ci_test_workflow_local
ci_test_workflow_local: ## Run the ci.yml workflow (lint and tests) locally using act
	$(call check_command,act)
	$(call print_info_section,Running ci workflow locally)
	$(Q)act --container-architecture linux/amd64 -W .github/workflows/ci.yml
	$(call print_success,Workflow completed)

.PHONY: ci_run_feeds_workflow_local
ci_run_feeds_workflow_local: ## Run the run_feeds.yml workflow locally using act
	$(call check_command,act)
	$(call print_info_section,Running run_feeds workflow locally)
	$(Q)act --container-architecture linux/amd64 -W .github/workflows/run_feeds.yml
	$(call print_success,Workflow completed)

.PHONY: ci_trigger_feeds_workflow
ci_trigger_feeds_workflow: ## Trigger the run_feeds.yml workflow on GitHub using gh
	$(call check_command,gh)
	$(call print_info,Triggering run_feeds workflow on GitHub)
	$(Q)gh workflow run run_feeds.yml
	$(call print_success,Workflow triggered)
