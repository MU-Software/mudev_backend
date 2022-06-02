# Import and add project routes here.
# If you want to make git not to track this file anymore,
# use `git update-index --skip-worktree app/api/project_route.py`
project_resource_routes = dict()

import app.api.playco as playco_route
project_resource_routes.update(playco_route.playco_resource_route)

import app.api.tool as tool_route
project_resource_routes.update(tool_route.tool_resource_route)
