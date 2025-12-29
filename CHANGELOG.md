# Changelog

All notable changes to Agent Sparrow will be documented in this file.

## [0.2.1](https://github.com/moonshubh/Agent_Sparrow/compare/v0.2.0...v0.2.1) (2025-12-29)


### Features

* **chat:** add message edit persistence via API ([1121cf4](https://github.com/moonshubh/Agent_Sparrow/commit/1121cf40d55cb96745ec57fddf196c46b02b56fd))
* **chat:** wire up functional regenerate button ([4b8d48d](https://github.com/moonshubh/Agent_Sparrow/commit/4b8d48d27f757c030dad2862dd31efe02ed0bb80))
* **feedback:** add message feedback with thumbs up/down and categories ([ac55adc](https://github.com/moonshubh/Agent_Sparrow/commit/ac55adc7d42a1f05f57d2a82dfa5d6f7f4adab63))
* **feedme:** enhance stats UI with dot-matrix cards and fix RPC mapping ([793cb44](https://github.com/moonshubh/Agent_Sparrow/commit/793cb444306802a8c1c2fe80bdc645986f2ddda7))
* **frontend:** add browser favicon/icon to metadata ([1c22a5f](https://github.com/moonshubh/Agent_Sparrow/commit/1c22a5f20fbd945eda90c749bcec74a76d24970d))
* **frontend:** persist chat timeline and artifacts ([5b8026c](https://github.com/moonshubh/Agent_Sparrow/commit/5b8026c406d444013a915776da0f45d5eb0c2ee4))
* **frontend:** polish header icons, sidebar avatars, and landing hero ([73ce47f](https://github.com/moonshubh/Agent_Sparrow/commit/73ce47f8e72ae111bc5fe3dbe885fcdead6da9fa))
* **frontend:** replace generic plus icon with bold modern cursive new-chat icon ([044d7f4](https://github.com/moonshubh/Agent_Sparrow/commit/044d7f4a39804140e6ca4e728b0f0e74f6440b72))
* **frontend:** UI improvements - FeedMe icon, sidebar user, and branding polish ([4b819c9](https://github.com/moonshubh/Agent_Sparrow/commit/4b819c924b8f417c89c5598d4438887cd566cf60))
* **frontend:** unify fonts, rearrange dock icons, and center sidebar alignment ([01db8d9](https://github.com/moonshubh/Agent_Sparrow/commit/01db8d90d2cfae5979ba8b9c3d79fd31b63edc99))
* **frontend:** unify modern square pen icon across sidebar and landing actions ([75772fc](https://github.com/moonshubh/Agent_Sparrow/commit/75772fc21c84b56a55d32429e08c03d08317dab3))
* **frontend:** update new chat icon to modern square pen to match design ([5600c51](https://github.com/moonshubh/Agent_Sparrow/commit/5600c51b8f8be128819fb3fd379b29a41794ff24))
* harden agent streaming and librechat experience ([0a7c1aa](https://github.com/moonshubh/Agent_Sparrow/commit/0a7c1aaf984d1a0ad774cca7ad32fe2ed3978673))
* harden unified agent tooling, models, and AG-UI flow ([b08999c](https://github.com/moonshubh/Agent_Sparrow/commit/b08999c845fc3c228551e021e8cf03f31a5ae340))
* harden unified agent tooling, models, and AG-UI flow ([edc398b](https://github.com/moonshubh/Agent_Sparrow/commit/edc398bff88f06b80213eb88be39a6880abde024))
* **icons:** replace legacy icons with consolidated feedme icon ([01664a2](https://github.com/moonshubh/Agent_Sparrow/commit/01664a22d1c543f73fa4af2f2ff78a2bcf83e721))
* **theme:** update fonts to Inter and darken backgrounds ([724a863](https://github.com/moonshubh/Agent_Sparrow/commit/724a86398e247c2cb0bfe2336ff51fd51b184e25))
* **theme:** update user bubble to Agent Sparrow blue ([6b925f3](https://github.com/moonshubh/Agent_Sparrow/commit/6b925f3ff781e7fd1674bc004eafd80a319e5e13))


### Bug Fixes

* address verification audit findings ([3cbd9d7](https://github.com/moonshubh/Agent_Sparrow/commit/3cbd9d74cb0b6a85c466c92bc29af9437e55b89f))
* **agent:** sanitize thinking trace and filter base64 images ([2780fdd](https://github.com/moonshubh/Agent_Sparrow/commit/2780fddac69eafd0787d2b0acf6b139e5f0c96f7))
* **api:** make chat session endpoints consistent for guest users ([fabaf5f](https://github.com/moonshubh/Agent_Sparrow/commit/fabaf5f8d87e7ee4e93100558d92e1e049e10420))
* **artifacts:** resolve persistence race condition and base64 image leak ([6e1daf6](https://github.com/moonshubh/Agent_Sparrow/commit/6e1daf66297607454f4bce794cd4fff7141af5c6))
* **chat:** fallback to Supabase REST for persistence ([18b1406](https://github.com/moonshubh/Agent_Sparrow/commit/18b14069d2ea7047eb28a2f1ffe1053277584486))
* **chat:** persistent sidebar artifacts and thinking timeline ([9bb7853](https://github.com/moonshubh/Agent_Sparrow/commit/9bb7853f1d41f8656cad113892a9e334eaf7c159))
* **fonts:** switch from Inter to system sans-serif fonts ([33ae2fb](https://github.com/moonshubh/Agent_Sparrow/commit/33ae2fb039ccb10bdd77358cd72814a5289ce644))
* **frontend:** CSS selector for message actions visibility ([3a26c46](https://github.com/moonshubh/Agent_Sparrow/commit/3a26c462eff808ef64db24ecaea1c5493773f405))
* **frontend:** improve browser icon quality with multiple sizes and formats ([2a42d7b](https://github.com/moonshubh/Agent_Sparrow/commit/2a42d7b770239fe1515f6cb9244c563e2a097a1e))
* **frontend:** improve sidebar conversation list spacing and branding ([54dc316](https://github.com/moonshubh/Agent_Sparrow/commit/54dc3165812787558270ffd0c11b4f0cae2d5d2c))
* **frontend:** prevent duplicate assistant persistence ([5fddabd](https://github.com/moonshubh/Agent_Sparrow/commit/5fddabd55872fdfd864425620e3316349a470812))
* **frontend:** track shared lib and remove duplicate ui folder ([bac21c0](https://github.com/moonshubh/Agent_Sparrow/commit/bac21c0adc41468a0a713f7542baa9aacb336002))
* **frontend:** use square cropped logo for browser icon to prevent squeezing ([4a41444](https://github.com/moonshubh/Agent_Sparrow/commit/4a414447fdf270b9ce65602314a971ac912f3b3d))
* **memory:** critical memory optimization for Celery workers ([514080a](https://github.com/moonshubh/Agent_Sparrow/commit/514080aef9571a4623c481e5eddf458713ca4de4))
* **railway:** remove frontend/ from railwayignore to enable frontend deployment ([a0cb669](https://github.com/moonshubh/Agent_Sparrow/commit/a0cb669b07db3e0898892a48387043ecccaf38ac))
* **release:** remove skip-github-release flag to fix PR creation ([16ae6e3](https://github.com/moonshubh/Agent_Sparrow/commit/16ae6e3b8daa86c9468edb619ac74fba1876b493))
* **security:** address critical code review findings ([f1d5a3c](https://github.com/moonshubh/Agent_Sparrow/commit/f1d5a3caa58397c0062d4051b3b153be1440b02d))
* **security:** address critical CodeRabbit review findings ([d2704ae](https://github.com/moonshubh/Agent_Sparrow/commit/d2704ae44fa97214b11f3ba9bd8aa1450f5ec3ef))
* **theme:** lighten background to charcoal gray ([#212121](https://github.com/moonshubh/Agent_Sparrow/issues/212121)) ([19d7a98](https://github.com/moonshubh/Agent_Sparrow/commit/19d7a98c89d00c9eeb603af3e982d09a0a513c10))
* **zendesk:** match manual note spacing ([3d4b98b](https://github.com/moonshubh/Agent_Sparrow/commit/3d4b98b10dcd3d9f79d9e6ad0ce09f617b9ce5df))
* **zendesk:** skip excluded tickets ([d02ebd1](https://github.com/moonshubh/Agent_Sparrow/commit/d02ebd187c40d757dea2e189859ec105234e50c4))


### Code Refactoring

* **css:** improve markdown spacing for better readability ([0aea35d](https://github.com/moonshubh/Agent_Sparrow/commit/0aea35d1482af578d6d0b52a7e339f01a9b3e75e))


### Miscellaneous

* prepare release ([bd0d71f](https://github.com/moonshubh/Agent_Sparrow/commit/bd0d71ff2179b9011e443e8d71128283d9d7d805))

## [0.2.0](https://github.com/moonshubh/Agent_Sparrow/compare/v0.1.0...v0.2.0) (2025-12-24)


### Features

* add lamp header to login page ([7cbbc9c](https://github.com/moonshubh/Agent_Sparrow/commit/7cbbc9c2f588a28cc58b13bdfacd160414e92b00))
* refresh login page with shadcn login-02 block and Google-only auth ([3b17d2e](https://github.com/moonshubh/Agent_Sparrow/commit/3b17d2ef5aecfd36706329b1a808eb59998c3e4b))
* refresh login page with shadcn login-02 block and Google-only auth ([4771b16](https://github.com/moonshubh/Agent_Sparrow/commit/4771b16aa7e60fee4ba05aff37aa26d94730ec3f))


### Bug Fixes

* address CodeRabbit review comments ([74db2f8](https://github.com/moonshubh/Agent_Sparrow/commit/74db2f8dc06bc75b7c320d48fcc15382e66891ab))
* avoid Zendesk reply truncation and greeting collapse ([2b5d41e](https://github.com/moonshubh/Agent_Sparrow/commit/2b5d41e531531531e8d0fef7e694a4b17a4942fe))
* implement proper 3D light physics for lamp glow effect ([c425689](https://github.com/moonshubh/Agent_Sparrow/commit/c42568972fd0bacf343e70b09cdcc8dc4e2a500f))
* refine login lamp header and hero image ([7e368cc](https://github.com/moonshubh/Agent_Sparrow/commit/7e368cc835d3fa2cd83144668894eeb36504e745))
* show login hero image on desktop ([a7cf53e](https://github.com/moonshubh/Agent_Sparrow/commit/a7cf53e0f12d28ab2a2794e3d278110c4f7778b6))

## [0.1.0] - 2025-01-01

### Features

- Initial release of Agent Sparrow unified agent system
- AG-UI protocol integration for native streaming conversations
- DeepAgents v0.2.5 middleware stack for context engineering
- FeedMe document processing module with Gemini vision API
- Zendesk integration with scheduler for ticket management
- Multi-provider LLM support (Google Gemini, xAI Grok)
- LangGraph orchestration for agent workflows
- Supabase integration for data persistence
- Model Registry for centralized configuration
- Human-in-the-loop interrupts via CUSTOM events
