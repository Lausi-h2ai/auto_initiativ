# Master CV prompt adaptations

The executable application-owned prompt is assembled by
`backend/app/agents/master_cv_builder_prompt.py`. It applies Auto Initiativ's
authority and schema rules before the pinned upstream workflow and route prompt.
The vendored prompts are references only and cannot grant tools or write state.
