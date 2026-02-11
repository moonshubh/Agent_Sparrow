# Changelog

## [0.2.4](https://github.com/moonshubh/Agent_Sparrow/compare/v0.2.3...v0.2.4) (2026-02-11)


### Bug Fixes

* add zendesk scheduler watchdog ([19a7a5c](https://github.com/moonshubh/Agent_Sparrow/commit/19a7a5c6370a06576c5d7e3b957e1b9983b37161))
* address devin and coderabbit review feedback ([6bcd679](https://github.com/moonshubh/Agent_Sparrow/commit/6bcd6792e90d84911a49481fd8bfa062709cf82a))
* address devin and coderabbit review feedback ([bf3657c](https://github.com/moonshubh/Agent_Sparrow/commit/bf3657c9e0110ac43e0dc2a43d3c67a11efc06f6))
* address Devin and CodeRabbit review findings ([442f7b2](https://github.com/moonshubh/Agent_Sparrow/commit/442f7b29d576a99f3f95399641cae230762307cf))
* **ci:** provide test env for API key encryption ([13add29](https://github.com/moonshubh/Agent_Sparrow/commit/13add298ed3806986ed34409fa823aab3271bfc9))
* guard feedme examples and enforce service key ([248f17b](https://github.com/moonshubh/Agent_Sparrow/commit/248f17b6383d56c94371ab66192f9a20f713b7ec))
* harden minimax mcp timeouts ([af55ef9](https://github.com/moonshubh/Agent_Sparrow/commit/af55ef925ebec4c185286dfe1683183ebd737d60))
* **memory:** prevent admin freeze on image-backed mb_playbook edits ([339a598](https://github.com/moonshubh/Agent_Sparrow/commit/339a59844eed5fd565110d71300b915e2af590e6))
* persist memory image sizing ([524bd28](https://github.com/moonshubh/Agent_Sparrow/commit/524bd28bd077e02e999a3f67fcf207d486ba81ba))
* **release:** add manual Slack dispatch and guard fromJSON ([5f77fe5](https://github.com/moonshubh/Agent_Sparrow/commit/5f77fe5ac8831ce98962c0b9f9dd2d540c651c1b))
* **release:** guard fromJSON against empty pr output ([bdd58e6](https://github.com/moonshubh/Agent_Sparrow/commit/bdd58e654da0d338bb6be655504d6531b9dd9d89))
* remove agent timeouts and harden fallback ([cd2ffde](https://github.com/moonshubh/Agent_Sparrow/commit/cd2ffdeb5cf1da15fa5e0f8aef851c404ad847ae))
* render memory metadata in dedicated visible drawer ([96d89e9](https://github.com/moonshubh/Agent_Sparrow/commit/96d89e9084550b3d87dc974d73d8152de294f420))
* restore metadata visibility in memory table edit modal ([5d03b15](https://github.com/moonshubh/Agent_Sparrow/commit/5d03b15164cd53426dc0357dd317b002ba09ec86))
* scheduler note logging and memory quick fixes ([6ba543f](https://github.com/moonshubh/Agent_Sparrow/commit/6ba543f0a81cde8a49467e5b3b1ee0d8bfd2495c))
* skip zendesk import without credentials ([ac97f44](https://github.com/moonshubh/Agent_Sparrow/commit/ac97f442a4fb396e902cf072a56c510facc2aa40))
* stabilize feedme + update deps ([9cb2260](https://github.com/moonshubh/Agent_Sparrow/commit/9cb22603de55bd26a3aab0d8930f05ab99957e68))
* unblock zendesk + feedme processing ([1683168](https://github.com/moonshubh/Agent_Sparrow/commit/16831687dc00b3bd793d1eb5476bcfae13a006a9))


### Performance

* **db:** add HNSW vector indexes, optimize RPCs, and tune autovacuum ([fe7eae8](https://github.com/moonshubh/Agent_Sparrow/commit/fe7eae8063f757eba077e4f78398d371eded125e))
* **db:** HNSW vector indexes, RPC optimization, autovacuum tuning ([a158bbe](https://github.com/moonshubh/Agent_Sparrow/commit/a158bbea78a1174c30e5350d46893c23a2c8dde9))

## [0.2.3](https://github.com/moonshubh/Agent_Sparrow/compare/v0.2.2...v0.2.3) (2026-02-02)


### Features

* add user-scoped workspace support ([91f5b6c](https://github.com/moonshubh/Agent_Sparrow/commit/91f5b6c00842d95c4bbd629e5d2553c6a2a94e66))
* **agents:** add Minimax M2.1 integration for subagents ([d2ddc03](https://github.com/moonshubh/Agent_Sparrow/commit/d2ddc0347a629281e532242aa8fb3d5ec4594d63))
* **agents:** comprehensive Minimax M2.1 integration with MCP support ([7cc2b5e](https://github.com/moonshubh/Agent_Sparrow/commit/7cc2b5e98b8ead55e1224ef8f5432372f3329db4))
* **agents:** Comprehensive Minimax M2.1 integration with MCP support ([2ae7689](https://github.com/moonshubh/Agent_Sparrow/commit/2ae7689c1bef683772afa04407fff12752f28ca1))
* improve memory list pagination ([af122f6](https://github.com/moonshubh/Agent_Sparrow/commit/af122f6d2ca65620c67fa5bf68279741bdb5dd40))
* improve Zendesk formatting, telemetry, spam guard ([2f14302](https://github.com/moonshubh/Agent_Sparrow/commit/2f14302fc9ae2f4ed1e92fa00f708fd06807185d))


### Bug Fixes

* address PR review feedback ([84f146f](https://github.com/moonshubh/Agent_Sparrow/commit/84f146f9be356e311dd0c74e66cfc8e4a977c623))
* address PR review feedback ([941e6a7](https://github.com/moonshubh/Agent_Sparrow/commit/941e6a7f17476427e4e69f94d3ffca2ba776c322))
* address PR review feedback for Zendesk formatting changes ([caab882](https://github.com/moonshubh/Agent_Sparrow/commit/caab8824b04c6d6617b2e60a9df7e6d8604047bb))
* address workspace guards and tests ([2d46611](https://github.com/moonshubh/Agent_Sparrow/commit/2d466112615241b04ecf189a049bc9c5753d9d95))
* avoid blocking spam guard note post ([e2e3c71](https://github.com/moonshubh/Agent_Sparrow/commit/e2e3c717bef0bdf6914b4a7734758ed0d27e40c2))
* enforce railpack builds on Railway ([e5bddc5](https://github.com/moonshubh/Agent_Sparrow/commit/e5bddc52c500ad60c032f39653cbd59915cf40d4))
* **feedme:** harden worker redis and clarify pdf model ([6f5c899](https://github.com/moonshubh/Agent_Sparrow/commit/6f5c899adbf67d18c7f221726dd92bc48fab529e))
* gate memory edit highlights to admins ([16b5cc8](https://github.com/moonshubh/Agent_Sparrow/commit/16b5cc81fff6d3a45f9a2814b089967c07e8ad54))
* harden attachment handling and SSE limits ([63a9f85](https://github.com/moonshubh/Agent_Sparrow/commit/63a9f85d50dcd89f43ec2570a4301e9215af2741))
* **logs:** prevent log analysis stalls on attachments ([027ec74](https://github.com/moonshubh/Agent_Sparrow/commit/027ec74f6fdd55ec2e7322493aa89fb5d242e588))
* **logs:** stabilize log file analysis ([d3ac3a0](https://github.com/moonshubh/Agent_Sparrow/commit/d3ac3a03fd65098976718e0cfd1e9a7c6819816d))
* **logs:** use Gemini response schema format ([bd14778](https://github.com/moonshubh/Agent_Sparrow/commit/bd14778c3836a5062673029ecbfcf56c4583bbc0))
* make railway entrypoint railpack-safe ([95b8ec0](https://github.com/moonshubh/Agent_Sparrow/commit/95b8ec092f15d3662ef813e71e929be7f15daa1c))
* prevent stale streaming overwrite ([f7e423a](https://github.com/moonshubh/Agent_Sparrow/commit/f7e423a161104404af0145799f62dfb10b01ef8f))
* **release:** add changelog to Slack notifications and sync manifest ([3df986f](https://github.com/moonshubh/Agent_Sparrow/commit/3df986fc7dbe585a7944d133f7b7cce75875c10c))
* **release:** add release-please version marker to __version__.py ([0783bdc](https://github.com/moonshubh/Agent_Sparrow/commit/0783bdcec28906b0ba396fe5b7f3945c75f85ea0))
* **release:** parse PR number from release-please JSON output ([e734a13](https://github.com/moonshubh/Agent_Sparrow/commit/e734a13b426f2f26e0c25db75a6fb4113088cab2))
* **release:** sync __version__.py with release manifest ([08bf9f9](https://github.com/moonshubh/Agent_Sparrow/commit/08bf9f9c80f494f5d1c18738428a676506b3db0d))
* **release:** use patch increments for pre-1.0 versions ([e7998a6](https://github.com/moonshubh/Agent_Sparrow/commit/e7998a605fdcd361bd4733c1a66950f58a3cebef))
* restore web search tools and escape handling ([7f8ae3c](https://github.com/moonshubh/Agent_Sparrow/commit/7f8ae3c9d9601fe8aa13e0e306751f899aa61deb))
* ship skills and gate firecrawl agent ([832c9d0](https://github.com/moonshubh/Agent_Sparrow/commit/832c9d097b35e79486cbde0b6914cee1b59019e5))
* stabilize sparrow chat UI and artifacts ([81960e0](https://github.com/moonshubh/Agent_Sparrow/commit/81960e03696f90a140f395b27193851ba8c54e4e))
* use cpu torch wheels on railway ([cfae0a7](https://github.com/moonshubh/Agent_Sparrow/commit/cfae0a7d27b0a13b3d6872423f8e44d35496b407))
* use Gemini 3 preview IDs ([79763e9](https://github.com/moonshubh/Agent_Sparrow/commit/79763e9f6fec5459dd431b6ddb5add62dd74960d))
* use nixpacks builder ([b42d364](https://github.com/moonshubh/Agent_Sparrow/commit/b42d364f12731103ff3c3012df500481d6fb4383))

## [0.2.2](https://github.com/moonshubh/Agent_Sparrow/compare/v0.2.1...v0.2.2) (2026-01-12)


### Features

* Add Memory UI system with knowledge graph visualization ([af6f446](https://github.com/moonshubh/Agent_Sparrow/commit/af6f4469d65948e0c456f57d7003a51a49b83c40))
* memory review workflow, YAML model config, artifact persistence & bug fixes ([2970773](https://github.com/moonshubh/Agent_Sparrow/commit/2970773723cefd0aa774ee18317a7ed86ef4e073))
* Memory UI system, YAML model config, bucket rate limiting & deep agents optimization ([bc20805](https://github.com/moonshubh/Agent_Sparrow/commit/bc208054a6156561a4a1ef7dff85221dbe0c8d12))
* **multimodal:** add vision fallback and memory guardrails ([c1cd387](https://github.com/moonshubh/Agent_Sparrow/commit/c1cd38775cf85f7e9114f311b5d1a5ccde75cd2a))


### Bug Fixes

* **agui:** redact data URLs in RAW events ([8a73a9f](https://github.com/moonshubh/Agent_Sparrow/commit/8a73a9f08ac8dda0e296feb1169ab630adf1b6a2))
* **frontend:** avoid duplicating attachments in forwardedProps ([d7d8f76](https://github.com/moonshubh/Agent_Sparrow/commit/d7d8f7691b0b4b5e4fad06490b7ef0319d01eb0d))
* **logging:** avoid attachment payload logs ([cc062f0](https://github.com/moonshubh/Agent_Sparrow/commit/cc062f0a6945b2aa56a3550deef3a65679ed5b40))
* reduce memory and external search usage ([cdab26a](https://github.com/moonshubh/Agent_Sparrow/commit/cdab26a21fea5887be492e07193fd88ab92eea36))
* reduce memory and external search usage ([257342c](https://github.com/moonshubh/Agent_Sparrow/commit/257342ca898172d0c71812771d4874c9dc800bad))
* remove thread_state import cycle ([10cf327](https://github.com/moonshubh/Agent_Sparrow/commit/10cf3279f9d7522454f2592c2e15ea0baf344aa3))
* restore rate-limited wrapper indentation ([38a6a43](https://github.com/moonshubh/Agent_Sparrow/commit/38a6a43fa7fef3a84d415dd52b99b7a0464fd212))
* SummarizationMiddleware compatibility across langchain versions ([2c83b77](https://github.com/moonshubh/Agent_Sparrow/commit/2c83b77279e86ee116b1898dcd158b3f2f3a8f6e))
* track memory libs and pin redis ([df17d1f](https://github.com/moonshubh/Agent_Sparrow/commit/df17d1fd65dbbc1b24bb6fd1e957146d86dbafcb))
* unblock memory reads and admin gating ([8fd2c64](https://github.com/moonshubh/Agent_Sparrow/commit/8fd2c6488aad4a3a70566b9ffbff2186901a9027))
* **zendesk:** update rate limiting defaults to match plan limits ([edf9139](https://github.com/moonshubh/Agent_Sparrow/commit/edf91398434febfbad58ad55d83cde186983af0c))
* **zendesk:** update rate limiting defaults to match plan limits ([50b7c30](https://github.com/moonshubh/Agent_Sparrow/commit/50b7c30d3b26bb128c7fa8e2408993b5972ce975))
