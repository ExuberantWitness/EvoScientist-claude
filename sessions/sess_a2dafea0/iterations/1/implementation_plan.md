# Implementation Plan: 如何改进actor critic算法提升Hopper-v4控制能力
plan_id: 3a07c312-df27-4240-a0b4-da998e059a16
workspace: /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/sessions/sess_a2dafea0
session_id: sess_a2dafea0
created_at: 2026-06-02T15:34:40.850723
iteration: 1
session_folder: ""

## 迭代上下文 (来自上次迭代)
- 迭代: 1
- CC atoms: 51 个 (experiment: 36, proposal: 7)
- CC relations: 13 条
- 上次已测算法: 12 个 (ATTENTION_PRIOR, DDPG, DP_DEPTH, GAIT_PHASE, REFUTED, SAC, TAYLOR_CURVATURE, TD3, TD_VARIANCE, TESTED, VALIDATED, VALUE_UNCERTAINTY)
- 已验证有效: ['ATTENTION_PRIOR', 'DDPG', 'DP_DEPTH', 'GAIT_PHASE', 'REFUTED', 'SAC', 'TAYLOR_CURVATURE', 'TD3', 'TD_VARIANCE', 'TESTED', 'VALIDATED', 'VALUE_UNCERTAINTY']
- 上次提案: 7 个 (AC熵正则化与状态依赖方差调整：Hopper-v4控制改进, 基于值函数不确定性量化的自适应熵调节AC算法, 基于动态规划深度与交互熵的混合异方差自适应AC算法, 基于Taylor展开的局部熵曲率自适应AC算法, 跨步态相位时序差分噪声驱动的动态熵调节AC算法)
- 基线策略: 上次已测: ['ATTENTION_PRIOR', 'DDPG', 'DP_DEPTH', 'GAIT_PHASE', 'REFUTED', 'SAC', 'TAYLOR_CURVATURE', 'TD3', 'TD_VARIANCE', 'TESTED', 'VALIDATED', 'VALUE_UNCERTAINTY']; 已验证有效: ['ATTENTION_PRIOR', 'DDPG', 'DP_DEPTH', 'GAIT_PHASE', 'REFUTED', 'SAC', 'TAYLOR_CURVATURE', 'TD3', 'TD_VARIANCE', 'TESTED', 'VALIDATED', 'VALUE_UNCERTAINTY']; 上次提出未完成: ['基于分位价值方差与T', '基于分位数价值方差与', '基于双CRITIC不', '基于双CRITIC方']; ELO Top-1: 基于分位数价值方差与TD误差异方差的自适应熵调节AC算法; ELO Top-2: 基于分位价值方差与TD误差异方差的自适应熵调节AC算法; ELO Top-3: 基于双Critic方差分解与注意力状态不确定性的自适应熵调节AC算法
- ELO 锦标赛 Top-1: 基于分位数价值方差与TD误差异方差的自适应熵调节AC算法

## 上下文
## Claim Chain 原子
{"id": "node_1780145142461_e13de494", "type": "fact", "title": "SAC", "content": "{\"source\": \"github_search\", \"category\": \"algorithms\", \"method\": \"SAC\"}", "tags": ["baseline", "user-confirmed", "algorithms"], "status": "active", "metadata": {"source": "github_search", "category": "algorithms", "iter": 0, "phase": "W2 问题分析", "created_at_iso": "2026-05-30T12:45:42.461320+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313629+00:00"}}
{"id": "node_1780145142464_2ee0cc05", "type": "fact", "title": "TD3", "content": "{\"source\": \"github_search\", \"category\": \"algorithms\", \"method\": \"TD3\"}", "tags": ["baseline", "user-confirmed", "algorithms"], "status": "active", "metadata": {"source": "github_search", "category": "algorithms", "iter": 0, "phase": "W2 问题分析", "created_at_iso": "2026-05-30T12:45:42.464903+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313689+00:00"}}
{"id": "node_1780145142466_b7d6013f", "type": "fact", "title": "DDPG", "content": "{\"source\": \"github_search\", \"category\": \"algorithms\", \"method\": \"DDPG\"}", "tags": ["baseline", "user-confirmed", "algorithms"], "status": "active", "metadata": {"source": "github_search", "category": "algorithms", "iter": 0, "phase": "W2 问题分析", "created_at_iso": "2026-05-30T12:45:42.466943+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313707+00:00"}}
{"id": "node_1780145142468_2e5d3859", "type": "fact", "title": "PPO", "content": "{\"source\": \"github_search\", \"category\": \"algorithms\", \"method\": \"PPO\"}", "tags": ["baseline", "user-confirmed", "algorithms"], "status": "active", "metadata": {"source": "github_search", "category": "algorithms", "iter": 0, "phase": "W2 问题分析", "created_at_iso": "2026-05-30T12:45:42.468893+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313721+00:00"}}
{"id": "node_1780145142470_82e50bde", "type": "fact", "title": "A2C", "content": "{\"source\": \"github_search\", \"category\": \"algorithms\", \"method\": \"A2C\"}", "tags": ["baseline", "user-confirmed", "algorithms"], "status": "active", "metadata": {"source": "github_search", "category": "algorithms", "iter": 0, "phase": "W2 问题分析", "created_at_iso": "2026-05-30T12:45:42.470956+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313734+00:00"}}
{"id": "node_1780145142472_b7d91cf7", "type": "fact", "title": "A3C", "content": "{\"source\": \"github_search\", \"category\": \"algorithms\", \"method\": \"A3C\"}", "tags": ["baseline", "user-confirmed", "algorithms"], "status": "active", "metadata": {"source": "github_search", "category": "algorithms", "iter": 0, "phase": "W2 问题分析", "created_at_iso": "2026-05-30T12:45:42.472898+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313747+00:00"}}
{"id": "node_1780145142474_8881cb00", "type": "fact", "title": "CleanRL", "content": "{\"source\": \"github_search\", \"category\": \"frameworks\", \"method\": \"CleanRL\"}", "tags": ["baseline", "user-confirmed", "frameworks"], "status": "active", "metadata": {"source": "github_search", "category": "frameworks", "iter": 0, "phase": "W2 问题分析", "created_at_iso": "2026-05-30T12:45:42.474980+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313760+00:00"}}
{"id": "node_1780145142476_663e672b", "type": "fact", "title": "Hopper-v4", "content": "{\"source\": \"github_search\", \"category\": \"benchmarks\", \"method\": \"Hopper-v4\"}", "tags": ["baseline", "user-confirmed", "benchmarks"], "status": "active", "metadata": {"source": "github_search", "category": "benchmarks", "iter": 0, "phase": "W2 问题分析", "created_at_iso": "2026-05-30T12:45:42.476892+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313773+00:00"}}
{"id": "node_1780145353332_2d2924cd", "type": "method", "title": "AC熵正则化与状态依赖方差调整：Hopper-v4控制改进", "content": "{\"hypothesis\": \"AC\\u7b97\\u6cd5\\u4e2d\\u71b5\\u6b63\\u5219\\u5316\\u7cfb\\u6570\\u56fa\\u5b9a\\u5bfc\\u81f4\\u63a2\\u7d22\\u4e0e\\u5229\\u7528\\u5931\\u8861\\u662fHopper-v4\\u63a7\\u5236\\u6027\\u80fd\\u74f6\\u9888\\uff1b\\u57fa\\u4e8e\\u72b6\\u6001\\u4f30\\u503c\\u7684\\u81ea\\u9002\\u5e94\\u65b9\\u5dee\\u8c03\\u6574\\u53ef\\u63d0\\u5347\\u7a33\\u5b9a\\u6027\\u4e0e\\u6700\\u7ec8\\u8868\\u73b0\\uff1b\\u73b0\\u6709PPO/SAC\\u7b49\\u57fa\\u7ebf\\u672a\\u80fd\\u89e3\\u51b3\\u5f02\\u65b9\\u5dee\\u566a\\u6001\\u4e0b\\u540c\\u8d28\\u71b5\\u6743\\u95ee\\u9898\\u3002\", \"method_sketch\": \"\\u5177\\u4f53\\u96be\\u70b9\\u8bc6\\u522b\\uff1a\\u5728Actor-Critic\\u6846\\u67b6\\u4e2d\\uff0c\\u71b5\\u6b63\\u5219\\u5316\\u9879\\uff08loss\\u9879\\uff1a-\\u03b2 * H(\\u03c0)) \\u7684\\u7cfb\\u6570\\u03b2\\u901a\\u5e38\\u662f\\u5168\\u5c40\\u56fa\\u5b9a\\u8d85\\u53c2\\u6570\\uff0c\\u5bfc\\u81f4\\u9ad8\\u52a8\\u6001\\u533a\\u57df\\uff08\\u5982Hopper\\u817e\\u7a7a\\u671f\\uff09\\u8fc7\\u5ea6\\u63a2\\u7d22\\u7834\\u574f\\u5e73\\u8861\\uff0c\\u800c\\u7a33\\u6001\\u533a\\u57df\\u63a2\\u7d22\\u4e0d\\u8db3\\u3002\\u56e0\\u679c\\u5206\\u6790\\uff1a\\u56fa\\u5b9a\\u03b2\\u65e0\\u6cd5\\u9002\\u5e94\\u73af\\u5883\\u5404\\u72b6\\u6001\\u4e0b\\u7684\\u4e0d\\u786e\\u5b9a\\u5ea6\\u5dee\\u5f02\\uff08\\u5f02\\u65b9\\u5dee\\uff09\\uff0c\\u9ad8\\u4f30\\u4f4e\\u8d28\\u91cf\\u52a8\\u4f5c\\u6216\\u9519\\u8fc7\\u7cbe\\u8c03\\uff0c\\u6700\\u7ec8\\u9020\\u6210\\u7b56\\u7565\\u9707\\u8361\\u4e0e\\u8df3\\u6b65\\u5931\\u8d25\\u3002\\u57fa\\u7ebf\\u4e3a\\u4f55\\u65e0\\u6cd5\\u89e3\\u51b3\\uff1aPPO\\u4f7f\\u7528\\u88c1\\u526a+\\u56fa\\u5b9a\\u71b5\\u7cfb\\u6570\\uff0cSAC\\u867d\\u81ea\\u52a8\\u8c03\\u6574\\u03b2\\u4f46\\u4ec5\\u57fa\\u4e8e\\u5e73\\u5747\\u71b5\\u76ee\\u6807\\uff0c\\u672a\\u8003\\u8651\\u72b6\\u6001\\u4f9d\\u8d56\\u7684\\u65b9\\u5dee\\u4fe1\\u606f\\uff0cHopper-v4\\u7684\\u8df3\\u8dc3\\u843d\\u70b9\\u968f\\u673a\\u6027\\u5927\\uff0c\\u5168\\u5c40\\u71b5\\u76ee\\u6807\\u4ecd\\u4f1a\\u6ede\\u540e\\u6216\\u8fc7\\u6fc0\\u3002\\u65b9\\u6848\\u601d\\u8def\\uff1a\\u6211\\u4eec\\u63d0\\u51fa\\u4e00\\u79cd\\u72b6\\u6001\\u4f9d\\u8d56\\u7684\\u81ea\\u9002\\u5e94\\u71b5\\u6b63\\u5219\\u5316\\u65b9\\u6cd5\\u2014\\u2014SA-Entropy\\u3002\\u9996\\u5148\\uff0c\\u4fdd\\u7559SAC\\u7684\\u53ccQ\\u7f51\\u7edc\\u67b6\\u6784\\u4ee5\\u51cf\\u8f7b\\u8fc7\\u4f30\\u8ba1\\uff08TD3\\u98ce\\u683c\\uff09\\uff0c\\u4f46\\u5728Actor loss\\u4e2d\\u5f15\\u5165\\u57fa\\u4e8e\\u5f53\\u524d\\u72b6\\u6001\\u4ef7\\u503c\\u4f30\\u8ba1\\u7684\\u65b9\\u5dee\\u7684\\u71b5\\u6743\\u91cd\\uff1a\\u03b2(s) = \\u03b20 * tanh(\\u03bb / (Var[V(s)] + \\u03b5))\\uff0c\\u5176\\u4e2dVar[V(s)]\\u7531critic ensemble\\u7684Q\\u503c\\u65b9\\u5dee\\u8fd1\\u4f3c\\u3002\\u5f53\\u72b6\\u6001\\u4ef7\\u503c\\u65b9\\u5dee\\u5927\\u65f6\\uff08\\u5373critic\\u9ad8\\u5ea6\\u4e0d\\u786e\\u5b9a\\uff09\\uff0c\\u03b2(s)\\u81ea\\u52a8\\u51cf\\u5c0f\\u4ee5\\u9f13\\u52b1\\u8c28\\u614e\\u63a2\\u7d22\\uff1b\\u53cd\\u4e4b\\u5219\\u589e\\u5927\\u4ee5\\u4fc3\\u8fdb\\u591a\\u6837\\u5316\\u3002\\u540c\\u65f6\\uff0c\\u5bf9critic loss\\u6dfb\\u52a0\\u68af\\u5ea6\\u88c1\\u526a\\u4e0e\\u5c42\\u5f52\\u4e00\\u5316\\uff0c\\u9632\\u6b62\\u65b9\\u5dee\\u7206\\u70b8\\u3002\\u6211\\u4eec\\u5728Hopper-v4\\u4e0a\\u9a8c\\u8bc1\\uff0c\\u8be5\\u65b9\\u6cd5\\u80fd\\u5e73\\u7a33\\u901a\\u8fc7\\u8df3\\u8dc3\\u76f8\\u4f4d\\u8f6c\\u6362\\uff0c\\u51cf\\u5c11\\u6454\\u5012\\u6b21\\u6570\\u3002\\u9884\\u671f\\u76f8\\u6bd4SAC\\u63d0\\u5347\\u5e73\\u5747\\u56de\\u62a5\\u7ea615%~20%\\u3002\", \"source_agent\": \"novel-academic-agent\", \"search_results_summary\": \"\\u6587\\u732e\\u68c0\\u7d22\\u91cd\\u70b9\\uff1a1. [SAC: Soft Actor-Critic, Haarnoja et al., 2018] \\u63d0\\u51fa\\u81ea\\u52a8\\u71b5\\u8c03\\u6574\\uff0c\\u4f46\\u5168\\u5c40\\u76ee\\u6807\\u5ffd\\u7565\\u72b6\\u6001\\u5f02\\u65b9\\u5dee\\uff1b2. [TD3: Fujimoto et al., 2018] \\u53ccQ\\u4e0e\\u5ef6\\u8fdf\\u66f4\\u65b0\\u51cf\\u8f7b\\u8fc7\\u4f30\\u8ba1\\uff0c\\u4f46\\u65e0\\u81ea\\u9002\\u5e94\\u71b5\\uff1b3. [VIME: Houthooft et al., 2016] \\u4f7f\\u7528\\u8d1d\\u53f6\\u65af\\u4e0d\\u786e\\u5b9a\\u6027\\u6307\\u5bfc\\u63a2\\u7d22\\uff0c\\u4f46\\u8ba1\\u7b97\\u4ee3\\u4ef7\\u9ad8\\uff1b4. [Adaptive Entropy via VAE, \\u672a\\u5927\\u89c4\\u6a21\\u9a8c\\u8bc1] \\u76ee\\u524d\\u65e0\\u76f4\\u63a5\\u72b6\\u6001\\u4f9d\\u8d56\\u71b5\\u6743\\u65b9\\u6848\\uff1b5. [Action-dependent variance, Levine 2014] \\u76f8\\u5173\\u4f46\\u975e\\u9996\\u8981\\u3002\\u641c\\u7d22\\u65e0\\u76f4\\u63a5\\u6539\\u8fdb\\u5339\\u914d\\uff0c\\u672c\\u65b9\\u6848\\u586b\\u8865\\u4e86\\u72b6\\u6001\\u81ea\\u9002\\u5e94\\u71b5\\u6b63\\u5219\\u5316\\u7684\\u7a7a\\u767d\\u3002\", \"phase\": \"W2 \\u95ee\\u9898\\u5206\\u6790\"}", "tags": ["proposal", "W2_问题分析"], "status": "active", "metadata": {"iter": 0, "phase": "W3 方案方向", "created_at_iso": "2026-05-30T12:49:13.332473+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313787+00:00"}}
{"id": "node_1780145355945_434f2bfe", "type": "method", "title": "基于值函数不确定性量化的自适应熵调节AC算法", "content": "{\"hypothesis\": \"AC\\u7b97\\u6cd5\\u4e2d\\u56fa\\u5b9a\\u6216\\u5168\\u5c40\\u71b5\\u8c03\\u8282\\u7cfb\\u6570\\u65e0\\u6cd5\\u5e94\\u5bf9Hopper-v4\\u72b6\\u6001\\u4f9d\\u8d56\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\uff0c\\u5bfc\\u81f4\\u9ad8\\u52a8\\u6001\\u533a\\u57df\\u8fc7\\u63a2\\u7d22\\u3001\\u7a33\\u6001\\u533a\\u57df\\u6b20\\u63a2\\u7d22\\uff1b\\u901a\\u8fc7\\u96c6\\u6210Q\\u7f51\\u7edc\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\u91cf\\u5316\\u5b9e\\u73b0\\u72b6\\u6001\\u81ea\\u9002\\u5e94\\u7684\\u71b5\\u6743\\u91cd\\uff0c\\u53ef\\u663e\\u8457\\u63d0\\u5347\\u7b56\\u7565\\u7a33\\u5065\\u6027\\u4e0e\\u6700\\u7ec8\\u6027\\u80fd\\u3002\\u73b0\\u6709SAC\\u867d\\u81ea\\u52a8\\u8c03\\u71b5\\u4f46\\u4ec5\\u57fa\\u4e8e\\u5168\\u5c40\\u76ee\\u6807\\uff0c\\u672a\\u8003\\u8651\\u5f02\\u65b9\\u5dee\\uff1bPPO\\u56fa\\u5b9a\\u71b5\\u7cfb\\u6570\\u5219\\u5b8c\\u5168\\u65e0\\u6cd5\\u81ea\\u9002\\u5e94\\u3002\", \"method_sketch\": \"\\uff081\\uff09\\u5177\\u4f53\\u96be\\u70b9\\u8bc6\\u522b\\uff08\\u5230\\u7f51\\u7edc\\u7ec4\\u4ef6/loss\\u9879\\u7ea7\\u522b\\uff09\\uff1a\\u5728Actor-Critic\\u6846\\u67b6\\u4e2d\\uff0cActor loss\\u901a\\u5e38\\u5305\\u542b\\u71b5\\u6b63\\u5219\\u9879\\uff1aL_actor = -E[Q(s,a) - \\u03b2 * log \\u03c0(a|s)]\\uff0c\\u5176\\u4e2d\\u03b2\\u4e3a\\u71b5\\u8c03\\u8282\\u7cfb\\u6570\\u3002\\u91c7\\u7528\\u56fa\\u5b9a\\u03b2\\uff08\\u5982PPO\\uff09\\u6216\\u5168\\u5c40\\u81ea\\u9002\\u5e94\\u03b2\\uff08\\u5982SAC\\u57fa\\u4e8e\\u5e73\\u5747\\u71b5\\u68af\\u5ea6\\u7684\\u5bf9\\u5076\\u68af\\u5ea6\\u66f4\\u65b0\\uff09\\u65f6\\uff0c\\u65e0\\u6cd5\\u53cd\\u6620\\u4e0d\\u540c\\u72b6\\u6001\\u4e0b\\u7684\\u65b9\\u5dee\\u5dee\\u5f02\\u3002\\u7279\\u522b\\u662fHopper-v4\\u4e2d\\uff0c\\u817e\\u7a7a\\u671fQ\\u503c\\u65b9\\u5dee\\u5927\\uff08\\u7531\\u4e8e\\u52a8\\u529b\\u5b66\\u968f\\u673a\\u6027\\uff09\\uff0c\\u800c\\u843d\\u5730\\u63a5\\u89e6\\u671f\\u65b9\\u5dee\\u5c0f\\u3002\\u56fa\\u5b9a\\u03b2\\u4f1a\\u5bfc\\u81f4\\u817e\\u7a7a\\u671f\\u8fc7\\u5ea6\\u63a2\\u7d22\\uff08\\u03b2\\u8fc7\\u5927\\u5219\\u7b56\\u7565\\u8fc7\\u4e8e\\u968f\\u673a\\uff0c\\u7834\\u574f\\u5e73\\u8861\\uff09\\uff0c\\u7a33\\u6001\\u671f\\u63a2\\u7d22\\u4e0d\\u8db3\\uff08\\u03b2\\u8fc7\\u5c0f\\u5219\\u8fc7\\u65e9\\u786e\\u5b9a\\u5316\\uff09\\u3002Critic\\u7f51\\u7edc\\uff1a\\u53ccQ (TD3)\\u6216SAC\\u7684\\u8f6fQ\\u66f4\\u65b0\\u4ecd\\u4f7f\\u7528\\u5168\\u5c40\\u7cfb\\u6570\\u3002\\uff082\\uff09\\u56e0\\u679c\\u5206\\u6790\\uff1a\\u8be5\\u96be\\u70b9\\u5bfc\\u81f4\\u6027\\u80fd\\u74f6\\u9888\\u7684\\u673a\\u5236\\u662f\\u2014\\u2014\\u5f02\\u65b9\\u5dee\\uff08heteroscedastic noise\\uff09\\u73af\\u5883\\u4e2d\\uff0c\\u5168\\u5c40\\u03b2\\u65e0\\u6cd5\\u5339\\u914d\\u6bcf\\u4e2a\\u72b6\\u6001\\u7684\\u6700\\u4f18\\u63a2\\u7d22-\\u5229\\u7528\\u6743\\u8861\\u3002Hopper-v4\\u8df3\\u8dc3\\u52a8\\u4f5c\\u9700\\u8981\\u7cbe\\u786e\\u65f6\\u5e8f\\uff0c\\u817e\\u7a7a\\u65f6\\u8fc7\\u5ea6\\u968f\\u673a\\u4f1a\\u5bfc\\u81f4\\u843d\\u5730\\u59ff\\u6001\\u5931\\u63a7\\uff1b\\u7a33\\u6001\\u671f\\u5219\\u9700\\u9002\\u5ea6\\u968f\\u673a\\u4ee5\\u907f\\u514d\\u5c40\\u90e8\\u6700\\u4f18\\u3002\\u56fa\\u5b9a\\u03b2\\u5f3a\\u8feb\\u7b56\\u7565\\u5728\\u6240\\u6709\\u72b6\\u6001\\u4e0b\\u4f7f\\u7528\\u76f8\\u540c\\u968f\\u673a\\u7a0b\\u5ea6\\uff0c\\u4ece\\u800c\\u5728\\u5173\\u952e\\u76f8\\u4f4d\\u4ea7\\u751f\\u6b21\\u4f18\\u89e3\\u3002\\uff083\\uff09baseline\\u4e3a\\u4f55\\u65e0\\u6cd5\\u89e3\\u51b3\\uff1aSAC\\uff08Haarnoja et al., 2018\\uff09\\u81ea\\u52a8\\u8c03\\u8282\\u03b2\\u7684\\u76ee\\u6807\\u662f\\u6700\\u5c0f\\u5316E[-\\u03b2 * (H_target - H(\\u03c0))]\\uff0cH_target\\u4e3a\\u5168\\u5c40\\u76ee\\u6807\\u71b5\\uff0c\\u4e0d\\u5206\\u89e3\\u5230\\u72b6\\u6001\\uff0c\\u56e0\\u6b64\\u65e0\\u6cd5\\u533a\\u5206\\u9ad8/\\u4f4e\\u4e0d\\u786e\\u5b9a\\u72b6\\u6001\\u3002PPO\\uff08Schulman et al., 2017\\uff09\\u4f7f\\u7528\\u56fa\\u5b9a\\u03b2\\u6216annealing\\uff0c\\u5b8c\\u5168\\u4f9d\\u8d56\\u88c1\\u526a\\uff0c\\u65e0\\u6cd5\\u81ea\\u9002\\u5e94\\u3002TD3\\uff08Fujimoto et al., 2018\\uff09\\u65e0\\u71b5\\u6b63\\u5219\\u3002\\u57fa\\u4e8e\\u4e0d\\u786e\\u5b9a\\u6027\\u7684\\u65b9\\u6cd5\\u5982VIME\\uff08Houthooft et al., 2016\\uff09\\u8ba1\\u7b97\\u8d1d\\u53f6\\u65af\\u4fe1\\u606f\\u589e\\u76ca\\uff0c\\u4f46\\u8ba1\\u7b97\\u590d\\u6742\\u4e14\\u672a\\u76f4\\u63a5\\u6574\\u5408\\u8fdbAC\\u71b5\\u8c03\\u8282\\u3002\\uff084\\uff09\\u65b9\\u6848\\u601d\\u8def\\uff1a\\u63d0\\u51faUncertainty-Weighted Adaptive Entropy (UWAE) \\u65b9\\u6cd5\\u3002\\u6838\\u5fc3\\uff1a\\u7528\\u96c6\\u6210Q\\u7f51\\u7edc\\uff08K\\u4e2a\\u5934\\uff09\\u7684\\u65b9\\u5dee\\u4f30\\u8ba1\\u72b6\\u6001\\u7ea7\\u4e0d\\u786e\\u5b9a\\u6027\\uff0c\\u52a8\\u6001\\u8c03\\u6574\\u8be5\\u72b6\\u6001\\u7684\\u71b5\\u6743\\u91cd\\u03b2(s)\\u3002\\u5177\\u4f53\\uff1aactor loss\\u6539\\u4e3a L_actor = -E[Q_avg(s,a) - \\u03b2(s) * log \\u03c0(a|s)]\\uff0c\\u5176\\u4e2d\\u03b2(s) = \\u03b20 * tanh( \\u03bb / (\\u03c3_Q(s) + \\u03b5) )\\uff0c\\u03b20\\u4e3a\\u57fa\\u7cfb\\u6570\\uff0c\\u03c3_Q(s) = std(Q_i(s,a) over ensemble)\\uff0c\\u03b5\\u9632\\u9664\\u96f6\\u3002\\u5f53\\u03c3_Q(s)\\u5927\\uff08\\u4e0d\\u786e\\u5b9a\\u9ad8\\uff09\\u65f6\\u03b2(s)\\u5c0f\\uff0c\\u9f13\\u52b1\\u786e\\u5b9a\\u6027\\uff08\\u4fdd\\u5b88\\u63a2\\u7d22\\uff09\\uff1b\\u5f53\\u03c3_Q(s)\\u5c0f\\uff08\\u786e\\u4fe1\\u9ad8\\uff09\\u65f6\\u03b2(s)\\u5927\\uff0c\\u9f13\\u52b1\\u968f\\u673a\\u6027\\uff08\\u5145\\u5206\\u63a2\\u7d22\\uff09\\u3002\\u6ce8\\u610f\\u8fd9\\u4e0e\\u76f4\\u89c9\\u76f8\\u53cd\\uff1a\\u4f20\\u7edf\\u8ba4\\u4e3a\\u9ad8\\u4e0d\\u786e\\u5b9a\\u5e94\\u591a\\u63a2\\u7d22\\uff0c\\u4f46Hopper\\u4e2d\\u9ad8\\u4e0d\\u786e\\u5b9a\\u6765\\u81ea\\u52a8\\u529b\\u5b66\\u968f\\u673a\\u6027\\uff08\\u5982\\u817e\\u7a7a\\u540e\\u7684\\u6df7\\u6c8c\\uff09\\uff0c\\u8fc7\\u5ea6\\u968f\\u673a\\u53cd\\u800c\\u7834\\u574f\\u5e73\\u8861\\uff0c\\u6545\\u5e94\\u964d\\u4f4e\\u968f\\u673a\\u6027\\u4ee5\\u4fdd\\u6301\\u7a33\\u5b9a\\uff1b\\u4f4e\\u4e0d\\u786e\\u5b9a\\u533a\\u5df2\\u53ef\\u9760\\uff0c\\u53ef\\u589e\\u968f\\u673a\\u6027\\u4ee5\\u7cbe\\u8c03\\u3002\\u6211\\u4eec\\u901a\\u8fc7\\u53cd\\u4e8b\\u5b9e\\u63a8\\u7406\\u5f97\\u51fa\\u6b64\\u8bbe\\u8ba1\\u3002\\u4e3a\\u7a33\\u5b9a\\u8bad\\u7ec3\\uff0c\\u5bf9critic ensemble\\u6dfb\\u52a0\\u5c42\\u5f52\\u4e00\\u5316\\uff08Ba et al., 2016\\uff09\\u548c\\u68af\\u5ea6\\u88c1\\u526a\\uff08clip grad norm 10.0\\uff09\\uff0c\\u5e76\\u91c7\\u7528TD3\\u98ce\\u683c\\u7684\\u5ef6\\u8fdf\\u7b56\\u7565\\u66f4\\u65b0\\u3002\\u9884\\u671f\\u5728Hopper-v4\\u4e0a\\u6bd4SAC\\u63d0\\u5347\\u5e73\\u5747\\u56de\\u62a515%-20%\\uff0c\\u4e14\\u964d\\u4f4e\\u6210\\u529f\\u7387\\u65b9\\u5dee\\u3002\", \"source_agent\": \"conservative-academic-agent\", \"search_results_summary\": \"\\u5173\\u952e\\u6587\\u732e\\uff1a1. [SAC] Haarnoja et al., 2018, Soft Actor-Critic: Off-Policy Maximum Entropy Deep RL with a Stochastic Actor, PMLR 80:1861-1870. \\u63d0\\u51fa\\u81ea\\u52a8\\u71b5\\u8c03\\u8282\\uff0c\\u4f46\\u5168\\u5c40\\u76ee\\u6807\\u71b5\\u672a\\u8003\\u8651\\u72b6\\u6001\\u5f02\\u65b9\\u5dee\\u30022. [PPO] Schulman et al., 2017, Proximal Policy Optimization Algorithms, arXiv:1707.06347. \\u56fa\\u5b9a\\u71b5\\u7cfb\\u6570\\uff0c\\u65e0\\u72b6\\u6001\\u81ea\\u9002\\u5e94\\u30023. [TD3] Fujimoto et al., 2018, Addressing Function Approximation Error in Actor-Critic Methods, PMLR 80:1587-1596. \\u53ccQ\\u51cf\\u8f7b\\u8fc7\\u4f30\\u8ba1\\uff0c\\u65e0\\u71b5\\u6b63\\u5219\\u30024. [VIME] Houthooft et al., 2016, VIME: Variational Information Maximizing Exploration, NIPS. \\u8d1d\\u53f6\\u65af\\u4fe1\\u606f\\u589e\\u76ca\\u9a71\\u52a8\\u63a2\\u7d22\\uff0c\\u8ba1\\u7b97\\u4ee3\\u4ef7\\u9ad8\\u30025. [Layer Normalization] Ba et al., 2016, Layer Normalization, arXiv:1607.06450. \\u7528\\u4e8e\\u7a33\\u5b9a\\u6df1\\u5ea6\\u7f51\\u7edc\\u30026. \\u641c\\u7d22\\u4e2d\\u672a\\u53d1\\u73b0\\u76f4\\u63a5\\u5c06\\u96c6\\u6210Q\\u4e0d\\u786e\\u5b9a\\u6027\\u7528\\u4e8e\\u72b6\\u6001\\u7ea7\\u81ea\\u9002\\u5e94\\u71b5\\u6743\\u7684\\u5de5\\u4f5c\\uff0c\\u672c\\u65b9\\u6848\\u586b\\u8865\\u7a7a\\u767d\\u3002\", \"phase\": \"W2 \\u95ee\\u9898\\u5206\\u6790\"}", "tags": ["proposal", "W2_问题分析"], "status": "active", "metadata": {"iter": 0, "phase": "W3 方案方向", "created_at_iso": "2026-05-30T12:49:15.945202+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313798+00:00"}}
{"id": "node_1780145546120_70c69439", "type": "method", "title": "基于动态规划深度与交互熵的混合异方差自适应AC算法", "content": "{\"hypothesis\": \"\\u9488\\u5bf9Hopper-v4\\u4e2d\\u5f02\\u65b9\\u5dee\\u52a8\\u6001\\u5bfc\\u81f4\\u7684\\u63a2\\u7d22-\\u5229\\u7528\\u5931\\u8861\\uff0c\\u63d0\\u51fa\\u4e00\\u79cd\\u7ed3\\u5408\\u52a8\\u6001\\u89c4\\u5212\\u6df1\\u5ea6\\uff08\\u503c\\u51fd\\u6570\\u8fed\\u4ee3\\u6b21\\u6570\\uff09\\u4e0e\\u4ea4\\u4e92\\u71b5\\uff08\\u7b56\\u7565\\u4e0e\\u76ee\\u6807\\u5206\\u5e03\\u7684KL\\u6563\\u5ea6\\uff09\\u7684\\u6df7\\u5408\\u81ea\\u9002\\u5e94\\u71b5\\u8c03\\u8282\\u65b9\\u6cd5\\uff0c\\u53ef\\u7cbe\\u51c6\\u5339\\u914d\\u6bcf\\u4e2a\\u72b6\\u6001\\u7684\\u6700\\u4f18\\u968f\\u673a\\u7a0b\\u5ea6\\uff0c\\u63d0\\u5347\\u56de\\u62a5\\u8d8530%\\u3002\", \"method_sketch\": \"\\uff081\\uff09\\u65b9\\u5411\\u63cf\\u8ff0\\u2014\\u2014\\u89e3\\u51b3\\u4ec0\\u4e48\\u96be\\u70b9\\uff1a\\n\\u672c\\u65b9\\u5411\\u89e3\\u51b3\\u7684\\u6838\\u5fc3\\u96be\\u70b9\\u662fAC\\u7b97\\u6cd5\\u5728\\u5f02\\u65b9\\u5dee\\u73af\\u5883\\uff08\\u5982Hopper-v4\\uff09\\u4e2d\\uff0c\\u56fa\\u5b9a\\u6216\\u5168\\u5c40\\u71b5\\u7cfb\\u6570\\u65e0\\u6cd5\\u9002\\u5e94\\u72b6\\u6001\\u4f9d\\u8d56\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\uff0c\\u5bfc\\u81f4\\u9ad8\\u52a8\\u6001\\u533a\\u57df\\uff08\\u817e\\u7a7a\\u671f\\uff09\\u8fc7\\u5ea6\\u63a2\\u7d22\\u3001\\u7a33\\u6001\\u533a\\u57df\\uff08\\u843d\\u5730\\u671f\\uff09\\u63a2\\u7d22\\u4e0d\\u8db3\\u3002\\n\\n\\uff082\\uff09\\u9488\\u5bf9\\u54ea\\u4e9b\\u96be\\u70b9\\u2014\\u2014\\u5173\\u8054W2\\u5206\\u6790\\uff1a\\nW2\\u5206\\u6790\\u5df2\\u6307\\u51fa\\u4e09\\u4e2a\\u5173\\u952e\\u74f6\\u9888\\uff1a\\n- \\u96be\\u70b9A\\uff1aCritic\\u4f30\\u8ba1\\u65b9\\u5dee\\u5728\\u65f6\\u7a7a\\u4e0a\\u5f02\\u8d28\\uff0c\\u817e\\u7a7a\\u671f\\u9ad8\\u65b9\\u5dee\\u3001\\u843d\\u5730\\u671f\\u4f4e\\u65b9\\u5dee\\uff0c\\u800c\\u5168\\u5c40\\u03b2\\u65e0\\u6cd5\\u5339\\u914d\\u3002\\n- \\u96be\\u70b9B\\uff1aActor\\u7b56\\u7565\\u5728\\u5173\\u952e\\u76f8\\u4f4d\\uff08\\u5982\\u817e\\u7a7a\\uff09\\u71b5\\u8fc7\\u5927\\u5bfc\\u81f4\\u63a7\\u5236\\u5d29\\u6e83\\uff0c\\u5728\\u5fae\\u8c03\\u9636\\u6bb5\\u71b5\\u8fc7\\u5c0f\\u9677\\u5165\\u5c40\\u90e8\\u6700\\u4f18\\u3002\\n- \\u96be\\u70b9C\\uff1a\\u73b0\\u6709\\u65b9\\u6cd5\\uff08SAC\\u3001PPO\\uff09\\u7f3a\\u4e4f\\u72b6\\u6001\\u7ea7\\u522b\\u7684\\u81ea\\u9002\\u5e94\\u673a\\u5236\\uff0c\\u4ec5\\u4f9d\\u8d56\\u5168\\u5c40\\u76ee\\u6807\\u6216\\u56fa\\u5b9a\\u7cfb\\u6570\\u3002\\n\\n\\u672c\\u65b9\\u6848\\u76f4\\u63a5\\u9488\\u5bf9\\u96be\\u70b9A\\u3001B\\u3001C\\uff0c\\u901a\\u8fc7\\u53cc\\u91cd\\u72b6\\u6001\\u81ea\\u9002\\u5e94\\u4fe1\\u53f7\\u7cbe\\u786e\\u8c03\\u8282\\u6bcf\\u4e2a\\u72b6\\u6001\\u7684\\u71b5\\u6743\\u91cd\\u3002\\n\\n\\uff083\\uff09\\u6280\\u672f\\u8def\\u5f84\\u6982\\u8981\\u2014\\u2014\\u7528\\u4ec0\\u4e48\\u65b9\\u6cd5\\uff1a\\n\\u63d0\\u51faDPD-IE\\uff08Dynamic Programming Depth & Interaction Entropy\\uff09\\u6df7\\u5408\\u81ea\\u9002\\u5e94\\u71b5\\u8c03\\u8282\\u7b97\\u6cd5\\u3002\\n\\n\\u6838\\u5fc3\\u521b\\u65b0\\uff1a\\na. \\u6784\\u5efa\\u96c6\\u6210Critic\\uff08K=7\\u4e2a\\u72ec\\u7acbQ\\u7f51\\u7edc\\uff09\\uff0c\\u8f93\\u51faQ\\u503c\\u96c6\\u5408\\uff0c\\u8ba1\\u7b97\\u6bcf\\u4e2a\\u72b6\\u6001-\\u52a8\\u4f5c\\u5bf9\\u7684\\u4e0d\\u786e\\u5b9a\\u6027U(s,a)=Var(Q_i(s,a))\\uff0c\\u5e76\\u805a\\u5408\\u4e3a\\u72b6\\u6001\\u4e0d\\u786e\\u5b9a\\u6027U(s)=E_a[U(s,a)]\\u3002\\nb. \\u5f15\\u5165\\u201c\\u52a8\\u6001\\u89c4\\u5212\\u6df1\\u5ea6\\u201d\\u5ea6\\u91cfDpl(s)\\uff0c\\u8868\\u793a\\u5f53\\u524d\\u72b6\\u6001\\u5728\\u503c\\u51fd\\u6570\\u66f4\\u65b0\\u4e2d\\u7ecf\\u8fc7\\u7684\\u8fed\\u4ee3\\u6b21\\u6570\\uff08\\u901a\\u8fc7\\u8bb0\\u5f55Q\\u7f51\\u7edc\\u8bad\\u7ec3\\u6b65\\u6570\\u4e2d\\u8be5\\u72b6\\u6001\\u88ab\\u8bbf\\u95ee\\u6b21\\u6570\\u53ca\\u5bf9\\u5e94TD\\u66f4\\u65b0\\u7d2f\\u8ba1\\u503c\\uff09\\uff0c\\u5f52\\u4e00\\u5316\\u540e\\u53cd\\u6620\\u8be5\\u72b6\\u6001\\u201c\\u88ab\\u5145\\u5206\\u4f18\\u5316\\u201d\\u7684\\u7a0b\\u5ea6\\u3002Dpl(s)\\u8d8a\\u5927\\uff0c\\u8bf4\\u660e\\u8be5\\u72b6\\u6001\\u5df2\\u7ecf\\u5b66\\u4e60\\u6210\\u719f\\uff0c\\u53ef\\u964d\\u4f4e\\u63a2\\u7d22\\u3002\\nc. \\u8ba1\\u7b97\\u201c\\u4ea4\\u4e92\\u71b5\\u201dI(s)=KL(\\u03c0(\\u00b7|s) || \\u03c0_target(\\u00b7|s))\\uff0c\\u5176\\u4e2d\\u03c0_target\\u4e3a\\u5ef6\\u8fdf\\u66f4\\u65b0\\u7684\\u76ee\\u6807\\u7b56\\u7565\\uff08\\u4f7f\\u7528\\u6307\\u6570\\u79fb\\u52a8\\u5e73\\u5747\\uff0c\\u66f4\\u65b0\\u7387\\u03c4=0.005\\uff09\\u3002I(s)\\u8861\\u91cf\\u7b56\\u7565\\u504f\\u79bb\\u76ee\\u6807\\u7a0b\\u5ea6\\uff0c\\u82e5\\u6563\\u5ea6\\u5927\\u8bf4\\u660e\\u7b56\\u7565\\u6b63\\u5728\\u5267\\u70c8\\u53d8\\u5316\\uff0c\\u9700\\u9650\\u5236\\u63a2\\u7d22\\u4ee5\\u907f\\u514d\\u9707\\u8361\\u3002\\nd. \\u878d\\u5408\\u4e09\\u8005\\u5f97\\u5230\\u6700\\u7ec8\\u71b5\\u7cfb\\u6570\\u03b2(s)=\\u03b20 * \\u03c3( -\\u03b11 * (U(s) - U_th) - \\u03b12 * (Dpl(s) - D_th) + \\u03b13 * (I(s) - I_th) )\\uff0c\\u5176\\u4e2d\\u03c3\\u4e3asigmoid\\uff0c\\u8d85\\u53c2\\u6570\\u901a\\u8fc7\\u5c11\\u91cf\\u7f51\\u683c\\u641c\\u7d22\\u786e\\u5b9a\\u3002\\ne. \\u5728SAC\\u6846\\u67b6\\u4e0a\\u5b9e\\u73b0\\uff1aActor loss\\u4e3aL_actor=-E[min(Q1,Q2) - \\u03b2(s)*H(\\u03c0)]\\uff1bCritic loss\\u4e3aL_critic=E[(r+\\u03b3V_target(s')-Q(s,a))^2]\\uff0c\\u5e76\\u6dfb\\u52a0TD3\\u5f0f\\u88c1\\u526a\\u4e0e\\u5c42\\u5f52\\u4e00\\u5316\\u3002\\nf. \\u8bad\\u7ec3\\u6d41\\u7a0b\\uff1a\\u6bcf\\u6b65\\u66f4\\u65b0Critic K\\u6b21\\uff0c\\u6bcfK\\u6b65\\u66f4\\u65b0Actor\\u4e0e\\u03b2(s)\\uff08\\u5ef6\\u8fdf\\u66f4\\u65b0\\uff09\\u3002\\u4f7f\\u7528\\u7ecf\\u9a8c\\u56de\\u653e\\u7f13\\u51b2\\uff0c\\u4f18\\u5148\\u91c7\\u6837\\u9ad8TD\\u8bef\\u5dee\\u6837\\u672c\\u3002\\n\\ng. \\u9884\\u671f\\u5728Hopper-v4\\u4e0a\\u8fbe\\u52304200-4500\\u5206\\uff0c\\u76f8\\u6bd4SAC\\u63d0\\u534730%\\u4ee5\\u4e0a\\uff0c\\u4e14\\u6454\\u5012\\u6b21\\u6570\\u51cf\\u5c1140%\\u3002\\n\\n\\uff084\\uff09\\u4e0ebaseline\\u7684\\u533a\\u5206\\u70b9\\uff1a\\n- \\u4e0eSAC\\uff08Haarnoja et al., 2018\\uff09\\u76f8\\u6bd4\\uff1aSAC\\u4f7f\\u7528\\u5168\\u5c40\\u03b2\\u901a\\u8fc7\\u6700\\u5c0f\\u5316E[-\\u03b2*(H-H_target)]\\u81ea\\u52a8\\u8c03\\u8282\\uff0c\\u65e0\\u6cd5\\u533a\\u5206\\u9ad8\\u4f4e\\u4e0d\\u786e\\u5b9a\\u72b6\\u6001\\u3002\\u672c\\u65b9\\u6848\\u4f7f\\u7528\\u72b6\\u6001\\u7ea7\\u522bU(s)\\u3001Dpl(s)\\u3001I(s)\\u4e09\\u91cd\\u4fe1\\u53f7\\uff0c\\u5b9e\\u73b0\\u7cbe\\u7ec6\\u81ea\\u9002\\u5e94\\u3002\\n- \\u4e0ePPO\\uff08Schulman et al., 2017\\uff09\\u76f8\\u6bd4\\uff1aPPO\\u4f7f\\u7528\\u56fa\\u5b9a\\u03b2\\u6216\\u9000\\u706b\\uff0c\\u65e0\\u81ea\\u9002\\u5e94\\u3002\\u672c\\u65b9\\u6848\\u5b8c\\u5168\\u52a8\\u6001\\u3002\\n- \\u4e0eVIME\\uff08Houthooft et al., 2016\\uff09\\u76f8\\u6bd4\\uff1aVIME\\u4f7f\\u7528\\u8d1d\\u53f6\\u65af\\u4fe1\\u606f\\u589e\\u76ca\\u8c03\\u6574\\u63a2\\u7d22\\u5956\\u52b1\\uff0c\\u4f46\\u8ba1\\u7b97\\u91cf\\u5927\\u4e14\\u4e0d\\u76f4\\u63a5\\u8c03\\u8282\\u71b5\\u7cfb\\u6570\\u3002\\u672c\\u65b9\\u6848\\u8f7b\\u91cf\\u4e14\\u76f4\\u63a5\\u3002\\n- \\u4e0e\\u4e4b\\u524d\\u8ba8\\u8bba\\u4e2d\\u7684SA-Entropy\\u6216UWAE\\u76f8\\u6bd4\\uff1a\\u589e\\u52a0\\u4e86\\u52a8\\u6001\\u89c4\\u5212\\u6df1\\u5ea6\\u5ea6\\u91cf\\uff0c\\u9632\\u6b62\\u65b9\\u5dee\\u4f30\\u8ba1\\u8bef\\u5dee\\u5bfc\\u81f4\\u7684\\u03b2\\u632f\\u8361\\uff1b\\u540c\\u65f6\\u4ea4\\u4e92\\u71b5\\u9879\\u80fd\\u5feb\\u901f\\u54cd\\u5e94\\u7b56\\u7565\\u7a81\\u53d8\\uff0c\\u589e\\u5f3a\\u7a33\\u5b9a\\u6027\\u3002\", \"source_agent\": \"novel-academic-agent\", \"search_results_summary\": \"\\u641c\\u7d22\\u5230\\u4ee5\\u4e0b\\u5173\\u952e\\u6587\\u732e\\uff1a\\n1. [SAC: Haarnoja et al., 2018] \\u63d0\\u51fa\\u81ea\\u52a8\\u71b5\\u8c03\\u6574\\uff0c\\u4f46\\u5168\\u5c40\\u76ee\\u6807\\u3002\\n2. [TD3: Fujimoto et al., 2018] \\u53ccQ\\u4e0e\\u5ef6\\u8fdf\\u66f4\\u65b0\\u3002\\n3. [VIME: Houthooft et al., 2016] \\u8d1d\\u53f6\\u65af\\u4fe1\\u606f\\u63a2\\u7d22\\uff0c\\u590d\\u6742\\u3002\\n4. [Uncertainty-based exploration: Bellemare et al., 2016] \\u4f7f\\u7528\\u5bc6\\u5ea6\\u6a21\\u578b\\u3002\\n5. [KL-regularized RL: Schulman et al., 2015] TRPO\\u81ea\\u7136\\u68af\\u5ea6\\u3002\\n6. [Meta-learning for exploration: Gupta et al., 2018] \\u8de8\\u4efb\\u52a1\\u81ea\\u9002\\u5e94\\u3002\\n7. [Action-dependent variance: Levine, 2014] \\u9ad8\\u65af\\u7b56\\u7565\\u65b9\\u5dee\\u8c03\\u8282\\u3002\\n\\u641c\\u5230\\u4e00\\u7bc7\\u6700\\u65b0\\u9884\\u5370\\u672c [2024] 'State-Adaptive Entropy: Dynamic Exploration for Continuous Control' \\u672a\\u6b63\\u5f0f\\u53d1\\u8868\\uff0c\\u4f46\\u4e0e\\u6846\\u67b6\\u90e8\\u5206\\u91cd\\u53e0\\uff0c\\u8bf4\\u660e\\u65b9\\u5411\\u524d\\u6cbf\\u3002\\u672c\\u65b9\\u6848\\u901a\\u8fc7\\u4e09\\u91cd\\u4fe1\\u53f7\\u7ec4\\u5408\\u4fdd\\u6301\\u72ec\\u7279\\u6027\\u3002\", \"phase\": \"W3 \\u65b9\\u6848\\u65b9\\u5411\"}", "tags": ["proposal", "W3_方案方向"], "status": "active", "metadata": {"iter": 0, "phase": "W3 方案方向", "created_at_iso": "2026-05-30T12:52:26.120430+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313808+00:00"}}
{"id": "node_1780145548895_bc2ecdb4", "type": "method", "title": "基于Taylor展开的局部熵曲率自适应AC算法", "content": "{\"hypothesis\": \"\\u9488\\u5bf9Hopper-v4\\u5f02\\u65b9\\u5dee\\u52a8\\u6001\\u5bfc\\u81f4\\u56fa\\u5b9a\\u71b5\\u7cfb\\u6570\\u63a2\\u7d22-\\u5229\\u7528\\u5931\\u8861\\uff0c\\u63d0\\u51fa\\u901a\\u8fc7\\u5c40\\u90e8\\u71b5\\u51fd\\u6570\\u66f2\\u7387\\uff08\\u4e8c\\u9636\\u5bfc\\u6570\\uff09\\u81ea\\u9002\\u5e94\\u8c03\\u8282\\u71b5\\u6743\\u91cd\\uff0c\\u7cbe\\u786e\\u5339\\u914d\\u6bcf\\u4e2a\\u72b6\\u6001\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\uff0c\\u76f8\\u8f83\\u4e8e\\u5168\\u5c40\\u5e73\\u5747\\u503c\\u65b9\\u6cd5\\uff0c\\u80fd\\u591f\\u66f4\\u7cbe\\u7ec6\\u5730\\u63a7\\u5236\\u63a2\\u7d22\\u529b\\u5ea6\\uff0c\\u63d0\\u5347\\u63a7\\u5236\\u7a33\\u5b9a\\u6027\\u548c\\u5e73\\u5747\\u56de\\u62a5\\u3002\", \"method_sketch\": \"(1)\\u65b9\\u5411\\u63cf\\u8ff0\\u2014\\u2014\\u89e3\\u51b3\\u4ec0\\u4e48\\u96be\\u70b9\\uff1a\\n\\u6838\\u5fc3\\u96be\\u70b9\\u662fAC\\u7b97\\u6cd5\\u5728\\u5f02\\u65b9\\u5dee\\u73af\\u5883\\uff08\\u5982Hopper-v4\\uff09\\u4e2d\\uff0c\\u56fa\\u5b9a\\u6216\\u5168\\u5c40\\u71b5\\u7cfb\\u6570\\u65e0\\u6cd5\\u9002\\u5e94\\u72b6\\u6001\\u4f9d\\u8d56\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\u3002\\u9ad8\\u52a8\\u6001\\u533a\\u57df\\uff08\\u817e\\u7a7a\\u671f\\uff09Q\\u503c\\u65b9\\u5dee\\u5927\\uff0c\\u8fc7\\u5ea6\\u63a2\\u7d22\\u7834\\u574f\\u5e73\\u8861\\uff1b\\u7a33\\u6001\\u533a\\u57df\\uff08\\u843d\\u5730\\u671f\\uff09\\u63a2\\u7d22\\u4e0d\\u8db3\\u5bfc\\u81f4\\u7b56\\u7565\\u65e9\\u719f\\u3002\\n\\n(2)\\u9488\\u5bf9\\u54ea\\u4e9b\\u96be\\u70b9\\u2014\\u2014\\u5173\\u8054W2\\u5206\\u6790\\uff1a\\n- \\u96be\\u70b9A\\uff1aCritic\\u4f30\\u8ba1\\u65b9\\u5dee\\u65f6\\u7a7a\\u5f02\\u8d28\\uff0c\\u5168\\u5c40\\u03b2\\u65e0\\u6cd5\\u5339\\u914d\\uff0c\\u5bfc\\u81f4\\u9ad8\\u65b9\\u5dee\\u533a\\u8fc7\\u5ea6\\u63a2\\u7d22\\u3001\\u4f4e\\u65b9\\u5dee\\u533a\\u63a2\\u7d22\\u4e0d\\u8db3\\u3002\\n- \\u96be\\u70b9B\\uff1aActor\\u7b56\\u7565\\u5728\\u5173\\u952e\\u76f8\\u4f4d\\uff08\\u817e\\u7a7a\\uff09\\u71b5\\u8fc7\\u5927\\u81f4\\u63a7\\u5d29\\u6e83\\uff0c\\u5fae\\u8c03\\u9636\\u6bb5\\u71b5\\u8fc7\\u5c0f\\u9677\\u5c40\\u90e8\\u6700\\u4f18\\u3002\\n- \\u96be\\u70b9C\\uff1a\\u73b0\\u65b9\\u6cd5\\uff08SAC\\u3001PPO\\uff09\\u7f3a\\u72b6\\u6001\\u7ea7\\u81ea\\u9002\\u5e94\\u673a\\u5236\\u3002\\n\\n(3)\\u6280\\u672f\\u8def\\u5f84\\u6982\\u8981\\u2014\\u2014\\u7528\\u4ec0\\u4e48\\u65b9\\u6cd5\\uff1a\\n\\u63d0\\u51faLocal Entropy Curvature Adaptation (LECA)\\uff0c\\u5229\\u7528\\u5c40\\u90e8\\u71b5\\u51fd\\u6570\\u7684\\u66f2\\u7387\\u4f5c\\u4e3a\\u81ea\\u9002\\u5e94\\u4fe1\\u53f7\\uff0c\\u8c03\\u8282\\u6bcf\\u4e2a\\u72b6\\u6001\\u7684\\u71b5\\u7cfb\\u6570\\u03b2(s)\\u3002\\u5728\\u7b56\\u7565\\u7f51\\u7edc\\u8f93\\u51fa\\u5c42\\uff08\\u901a\\u5e38\\u7528Softmax\\u6216Gaussian\\uff09\\uff0c\\u5bf9\\u6bcf\\u4e2a\\u72b6\\u6001\\u7684\\u7b56\\u7565\\u5206\\u5e03\\u03c0(\\u00b7|s)\\u8ba1\\u7b97\\u5176\\u5bf9\\u6570\\u6982\\u7387\\u5173\\u4e8e\\u52a8\\u4f5c\\u7684Hessian\\u77e9\\u9635\\uff0c\\u53d6\\u5176\\u8ff9\\uff08Trace\\uff09\\u4f5c\\u4e3a\\u72b6\\u6001\\u71b5\\u66f2\\u7387\\u6307\\u6807\\uff1aC(s) = Trace(\\u2207_a^2 log \\u03c0(a|s))\\u3002\\u5f53C(s)\\u8f83\\u5927\\u65f6\\uff0c\\u7b56\\u7565\\u9762\\u5728\\u52a8\\u4f5c\\u7a7a\\u95f4\\u5f2f\\u66f2\\u5267\\u70c8\\uff0c\\u8868\\u660e\\u8be5\\u72b6\\u6001\\u5bf9\\u52a8\\u4f5c\\u9009\\u62e9\\u654f\\u611f\\uff0c\\u9700\\u964d\\u4f4e\\u63a2\\u7d22\\uff08\\u51cf\\u5c0f\\u03b2\\uff09\\uff1b\\u53cd\\u4e4b\\uff0cC(s)\\u5c0f\\u5219\\u7b56\\u7565\\u9762\\u5e73\\u5766\\uff0c\\u53ef\\u589e\\u52a0\\u63a2\\u7d22\\u3002\\u8ba1\\u7b97\\u4e0eC(s)\\u76f8\\u53cd\\u53d8\\u5316\\u7684\\u03b2(s) = \\u03b20 / (1 + \\u03bb*C(s))\\uff0c\\u5176\\u4e2d\\u03bb\\u4e3a\\u8c03\\u8282\\u7cfb\\u6570\\u3002\\u5728SAC\\u6846\\u67b6\\u4e2d\\uff0cActor loss\\u4e3aL_actor = -E[Q(s,a) - \\u03b2(s)*H(\\u03c0(\\u00b7|s))]\\uff0cCritic\\u4fdd\\u6301\\u53ccQ\\u4e0e\\u8f6f\\u66f4\\u65b0\\uff0c\\u5e76\\u6dfb\\u52a0\\u68af\\u5ea6\\u88c1\\u526a\\u9632\\u6b62\\u66f2\\u7387\\u7206\\u70b8\\u3002\\n\\n(4)\\u4e0ebaseline\\u7684\\u533a\\u5206\\u70b9\\uff1a\\n- \\u4e0eSAC\\u7684\\u5168\\u5c40\\u81ea\\u52a8\\u03b2\\u76f8\\u6bd4\\uff0cSAC\\u4ec5\\u5339\\u914d\\u5e73\\u5747\\u76ee\\u6807\\u71b5\\uff0c\\u800cLECA\\u57fa\\u4e8e\\u5c40\\u90e8\\u51e0\\u4f55\\u63d0\\u4f9b\\u72b6\\u6001\\u7279\\u5f02\\u6027\\u03b2\\u3002\\n- \\u4e0ePPO\\u56fa\\u5b9a\\u03b2\\u76f8\\u6bd4\\uff0cLECA\\u52a8\\u6001\\u8c03\\u6574\\uff0c\\u4e14\\u4e0d\\u5f15\\u5165\\u989d\\u5916\\u96c6\\u6210\\u7f51\\u7edc\\u3002\\n- \\u4e0e\\u57fa\\u4e8e\\u96c6\\u6210\\u65b9\\u5dee\\u7684\\u65b9\\u6cd5\\u76f8\\u6bd4\\uff0cLECA\\u8ba1\\u7b97\\u91cf\\u5c0f\\uff08\\u4e00\\u6b21\\u53cd\\u5411\\u4f20\\u64ad\\u5373\\u53ef\\u5f97\\u66f2\\u7387\\uff09\\uff0c\\u6613\\u4e8e\\u5b9e\\u73b0\\u3002\", \"source_agent\": \"conservative-academic-agent\", \"search_results_summary\": \"1. [SAC: Haarnoja et al., 2018] \\u81ea\\u52a8\\u71b5\\u8c03\\u8282\\u5168\\u5c40\\u03b2\\uff1b2. [PPO: Schulman et al., 2017] \\u56fa\\u5b9a\\u71b5\\u7cfb\\u6570\\uff1b3. [Natural gradient: Amari, 1998] \\u5229\\u7528Fisher\\u4fe1\\u606f\\u77e9\\u9635\\u4e8c\\u9636\\u4fe1\\u606f\\u4f18\\u5316\\uff0c\\u542f\\u53d1\\u4e86\\u5229\\u7528Hessian\\u66f2\\u7387\\uff1b4. [Variational inference: Blei et al., 2017] \\u4e2d\\u5229\\u7528\\u66f2\\u7387\\u81ea\\u9002\\u5e94\\u5b66\\u4e60\\u7387\\uff0c\\u7c7b\\u6bd4\\u7528\\u4e8e\\u81ea\\u9002\\u5e94\\u71b5\\uff1b5. [Curvature-based exploration: Makarova et al., 2020] \\u4f7f\\u7528\\u9ad8\\u65af\\u8fc7\\u7a0b\\u66f2\\u7387\\u6307\\u5bfc\\u63a2\\u7d22\\uff0c\\u4f46\\u672a\\u7528\\u4e8eAC\\u71b5\\u8c03\\u8282\\u3002\\u672c\\u65b9\\u6848\\u9996\\u6b21\\u5c06\\u5c40\\u90e8\\u71b5\\u66f2\\u7387\\u76f4\\u63a5\\u7528\\u4e8eAC\\u81ea\\u9002\\u5e94\\u71b5\\u6743\\u91cd\\u3002\", \"phase\": \"W3 \\u65b9\\u6848\\u65b9\\u5411\"}", "tags": ["proposal", "W3_方案方向"], "status": "active", "metadata": {"iter": 0, "phase": "W3 方案方向", "created_at_iso": "2026-05-30T12:52:28.895576+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313817+00:00"}}
{"id": "node_1780145551770_904893ba", "type": "method", "title": "跨步态相位时序差分噪声驱动的动态熵调节AC算法", "content": "{\"hypothesis\": \"Hopper-v4\\u7684\\u5f02\\u65b9\\u5dee\\u6027\\u6e90\\u4e8e\\u6b65\\u6001\\u5468\\u671f\\u4e2d\\u4e0d\\u540c\\u76f8\\u4f4d\\uff08\\u817e\\u7a7a\\u3001\\u843d\\u5730\\u3001\\u652f\\u6491\\uff09\\u7684\\u52a8\\u529b\\u5b66\\u968f\\u673a\\u6027\\u5dee\\u5f02\\uff0c\\u5bfc\\u81f4TD\\u8bef\\u5dee\\u65b9\\u5dee\\u5728\\u5404\\u76f8\\u4f4d\\u5448\\u73b0\\u5468\\u671f\\u6027\\u6ce2\\u52a8\\u3002\\u82e5\\u5c06\\u71b5\\u7cfb\\u6570\\u03b2\\u8bbe\\u8ba1\\u4e3a\\u76f8\\u4f4d\\u76f8\\u5173\\u51fd\\u6570\\uff0c\\u53ef\\u7cbe\\u51c6\\u5339\\u914d\\u6bcf\\u4e2a\\u76f8\\u4f4d\\u7684\\u63a2\\u7d22\\u9700\\u6c42\\uff0c\\u4ece\\u800c\\u663e\\u8457\\u63d0\\u5347\\u7b56\\u7565\\u7a33\\u5b9a\\u6027\\u4e0e\\u56de\\u62a5\\u3002\", \"method_sketch\": \"(1)\\u65b9\\u5411\\u63cf\\u8ff0\\u2014\\u2014\\u89e3\\u51b3\\u4ec0\\u4e48\\u96be\\u70b9\\uff1a\\u672c\\u65b9\\u5411\\u89e3\\u51b3\\u7684\\u6838\\u5fc3\\u96be\\u70b9\\u662fAC\\u7b97\\u6cd5\\u5728Hopper-v4\\u8fd9\\u7c7b\\u5177\\u6709\\u5468\\u671f\\u6027\\u52a8\\u529b\\u5b66\\u7684\\u5f02\\u65b9\\u5dee\\u73af\\u5883\\u4e2d\\uff0c\\u56fa\\u5b9a\\u6216\\u5168\\u5c40\\u81ea\\u9002\\u5e94\\u71b5\\u7cfb\\u6570\\u65e0\\u6cd5\\u5339\\u914d\\u72b6\\u6001\\u4f9d\\u8d56\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\u3002\\u5177\\u4f53\\u8868\\u73b0\\u4e3a\\uff1a\\u817e\\u7a7a\\u671f\\uff08\\u9ad8\\u52a8\\u6001\\uff09TD\\u8bef\\u5dee\\u65b9\\u5dee\\u5927\\uff0c\\u71b5\\u8fc7\\u5927\\u5bfc\\u81f4\\u7b56\\u7565\\u968f\\u673a\\u6027\\u7834\\u574f\\u843d\\u5730\\u59ff\\u6001\\uff1b\\u843d\\u5730\\u671f\\uff08\\u4f4e\\u52a8\\u6001\\uff09\\u65b9\\u5dee\\u5c0f\\uff0c\\u71b5\\u8fc7\\u5c0f\\u5bfc\\u81f4\\u7b56\\u7565\\u65e9\\u719f\\u65e0\\u6cd5\\u7cbe\\u7ec6\\u5fae\\u8c03\\u3002\\u73b0\\u6709SAC\\u4ec5\\u57fa\\u4e8e\\u5168\\u5c40\\u5e73\\u5747\\u76ee\\u6807\\u71b5\\u8c03\\u8282\\u03b2\\uff0cPPO\\u56fa\\u5b9a\\u03b2\\u5747\\u65e0\\u6cd5\\u9002\\u5e94\\u8fd9\\u79cd\\u5468\\u671f\\u6027\\u5f02\\u65b9\\u5dee\\u3002\\n\\n(2)\\u9488\\u5bf9\\u54ea\\u4e9b\\u96be\\u70b9\\u2014\\u2014\\u5173\\u8054W2\\u5206\\u6790\\uff1aW2\\u5206\\u6790\\u5df2\\u8bc6\\u522b\\u4e09\\u4e2a\\u5173\\u952e\\u74f6\\u9888\\uff1a\\u96be\\u70b9A\\uff1aCritic\\u4f30\\u8ba1\\u65b9\\u5dee\\u65f6\\u7a7a\\u5f02\\u8d28\\uff08\\u817e\\u7a7a\\u9ad8\\u65b9\\u5dee\\u3001\\u843d\\u5730\\u4f4e\\u65b9\\u5dee\\uff09\\uff1b\\u96be\\u70b9B\\uff1aActor\\u7b56\\u7565\\u5728\\u5173\\u952e\\u76f8\\u4f4d\\u71b5\\u8fc7\\u5927/\\u8fc7\\u5c0f\\uff1b\\u96be\\u70b9C\\uff1a\\u7f3a\\u4e4f\\u72b6\\u6001\\u7ea7\\u81ea\\u9002\\u5e94\\u673a\\u5236\\u3002\\u672c\\u65b9\\u6848\\u76f4\\u63a5\\u9488\\u5bf9\\u6240\\u6709\\u4e09\\u4e2a\\u96be\\u70b9\\uff0c\\u901a\\u8fc7\\u6784\\u5efa\\u6b65\\u6001\\u76f8\\u4f4d\\u4f30\\u8ba1\\u5668\\uff0c\\u5c06TD\\u8bef\\u5dee\\u65b9\\u5dee\\u4e0e\\u76f8\\u4f4d\\u8026\\u5408\\uff0c\\u5b9e\\u73b0\\u7cbe\\u786e\\u7684\\u72b6\\u6001\\u7ea7\\u71b5\\u8c03\\u8282\\u3002\\n\\n(3)\\u6280\\u672f\\u8def\\u5f84\\u6982\\u8981\\u2014\\u2014\\u7528\\u4ec0\\u4e48\\u65b9\\u6cd5\\uff1a\\u63d0\\u51faPhase-Dependent Adaptive Entropy (PDAE)\\u7b97\\u6cd5\\u3002\\u6838\\u5fc3\\u521b\\u65b0\\uff1aa. \\u76f8\\u4f4d\\u4f30\\u8ba1\\u5668\\uff1a\\u4f7f\\u7528\\u4e00\\u4e2a\\u8f7b\\u91cf\\u7ea7LSTM\\u7f51\\u7edc\\uff0c\\u4ee5\\u8fde\\u7eedN\\u5e27\\u72b6\\u6001\\u5e8f\\u5217\\uff08N=10\\uff09\\u4f5c\\u4e3a\\u8f93\\u5165\\uff0c\\u8f93\\u51fa\\u5f53\\u524d\\u6b65\\u6001\\u76f8\\u4f4d\\u03c6\\u2208[0,1]\\uff080=\\u521a\\u843d\\u5730\\uff0c0.5=\\u817e\\u7a7a\\u6700\\u9ad8\\u70b9\\uff0c1=\\u518d\\u6b21\\u843d\\u5730\\uff09\\u3002\\u8bad\\u7ec3\\u65f6\\uff0c\\u5229\\u7528Hopper-v4\\u7684\\u5173\\u8282\\u4f4d\\u7f6e\\u901f\\u5ea6\\u8ba1\\u7b97\\u811a\\u90e8\\u63a5\\u89e6\\u6807\\u5fd7\\u4f5c\\u4e3a\\u5f31\\u76d1\\u7763\\u4fe1\\u53f7\\u3002b. \\u76f8\\u4f4d\\u6761\\u4ef6\\u5316\\u71b5\\u7cfb\\u6570\\uff1a\\u03b2(\\u03c6)=\\u03b20 * (1 - \\u03b1 * sin(\\u03c0\\u03c6))\\uff0c\\u5176\\u4e2d\\u03b1\\u2208[0,1]\\u4e3a\\u8c03\\u8282\\u5f3a\\u5ea6\\u3002\\u817e\\u7a7a\\u671f\\uff08\\u03c6\\u22480.5\\uff09\\u03b2\\u6700\\u5c0f\\uff0c\\u843d\\u5730\\u671f\\uff08\\u03c6\\u22480\\u62161\\uff09\\u03b2\\u6700\\u5927\\u3002c. \\u4e0eTD\\u8bef\\u5dee\\u65b9\\u5dee\\u878d\\u5408\\uff1a\\u989d\\u5916\\u4f30\\u8ba1TD\\u8bef\\u5dee\\u65b9\\u5dee\\u7684\\u76f8\\u4f4d\\u6761\\u4ef6\\u5316\\u6307\\u6570\\u6ed1\\u52a8\\u5e73\\u5747\\uff1a\\u03c3\\u00b2(\\u03c6,t)=\\u03c1\\u03c3\\u00b2(\\u03c6,t-1)+(1-\\u03c1)(\\u03b4_t\\u00b2)\\uff0c\\u03b4_t\\u4e3a\\u5f53\\u524dTD\\u8bef\\u5dee\\u3002\\u6700\\u7ec8\\u03b2(s)=\\u03b2(\\u03c6) * sigmoid( -\\u03b7 * (\\u03c3\\u00b2(\\u03c6,t) - \\u03c4) )\\uff0c\\u5176\\u4e2d\\u03c4\\u4e3a\\u9608\\u503c\\uff0c\\u03b7\\u4e3a\\u589e\\u76ca\\u3002d. \\u7b97\\u6cd5\\u6846\\u67b6\\u57fa\\u4e8eSAC\\uff0cActor loss\\u4e3aL_actor = -E[Q(s,a) - \\u03b2(s)*H(\\u03c0)]\\uff0cCritic\\u4fdd\\u7559\\u53ccQ\\u4e0e\\u8f6f\\u66f4\\u65b0\\u3002\\u6240\\u6709\\u7ec4\\u4ef6\\u7aef\\u5230\\u7aef\\u8bad\\u7ec3\\uff0c\\u76f8\\u4f4d\\u4f30\\u8ba1\\u5668\\u4e0e\\u4e3b\\u7f51\\u7edc\\u5171\\u4eab\\u5e95\\u5c42\\u7f16\\u7801\\u5668\\u3002\\n\\n(4)\\u4e0ebaseline\\u7684\\u533a\\u5206\\u70b9\\uff1a\\u4e0eSAC\\u7684\\u5168\\u5c40\\u81ea\\u52a8\\u03b2\\u76f8\\u6bd4\\uff0cSAC\\u4ec5\\u5339\\u914d\\u5e73\\u5747\\u76ee\\u6807\\u71b5\\uff0c\\u800cPDAE\\u57fa\\u4e8e\\u76f8\\u4f4d\\u4e0e\\u566a\\u58f0\\u65b9\\u5dee\\u63d0\\u4f9b\\u7ec6\\u7c92\\u5ea6\\u72b6\\u6001\\u7279\\u5f02\\u6027\\u8c03\\u8282\\u3002\\u4e0ePPO\\u56fa\\u5b9a\\u03b2\\u76f8\\u6bd4\\uff0cPDAE\\u52a8\\u6001\\u8c03\\u6574\\u4e14\\u4e0d\\u4f9d\\u8d56\\u88c1\\u526a\\u3002\\u4e0e\\u57fa\\u4e8e\\u96c6\\u6210\\u65b9\\u5dee\\u7684\\u65b9\\u6cd5\\uff08\\u5982HAER\\uff09\\u76f8\\u6bd4\\uff0cPDAE\\u5229\\u7528\\u5468\\u671f\\u7ed3\\u6784\\u4fe1\\u606f\\uff0c\\u65e0\\u9700\\u989d\\u5916K\\u4e2a\\u7f51\\u7edc\\uff0c\\u8ba1\\u7b97\\u6548\\u7387\\u9ad8\\uff1b\\u4e0e\\u57fa\\u4e8e\\u5c40\\u90e8\\u66f2\\u7387\\u7684\\u65b9\\u6cd5\\uff08\\u5982LECA\\uff09\\u76f8\\u6bd4\\uff0cPDAE\\u4e0d\\u5bf9\\u7b56\\u7565\\u5c42\\u6c42\\u4e8c\\u9636\\u5bfc\\uff0c\\u6570\\u503c\\u66f4\\u7a33\\u5b9a\\u3002\\u672c\\u65b9\\u6848\\u9996\\u6b21\\u5c06\\u6b65\\u6001\\u76f8\\u4f4d\\u663e\\u5f0f\\u5efa\\u6a21\\u7528\\u4e8eAC\\u81ea\\u9002\\u5e94\\u71b5\\u8c03\\u8282\\u3002\", \"source_agent\": \"novel-engineering-agent\", \"search_results_summary\": \"1. [SAC: Haarnoja et al., 2018] \\u81ea\\u52a8\\u71b5\\u8c03\\u6574\\u5168\\u5c40\\u03b2\\uff1b2. [PPO: Schulman et al., 2017] \\u56fa\\u5b9a\\u71b5\\u7cfb\\u6570\\uff1b3. [TD3: Fujimoto et al., 2018] \\u53ccQ\\u4e0e\\u5ef6\\u8fdf\\u66f4\\u65b0\\uff1b4. [PLAS: Zhou et al., 2020] \\u5229\\u7528\\u6f5c\\u5728\\u7a7a\\u95f4\\u7ea6\\u675f\\uff0c\\u542f\\u53d1\\u4e86\\u76f8\\u4f4d\\u6761\\u4ef6\\u5316\\uff1b5. [Phase-based control in locomotion: Ijspeert, 2008] \\u4e2d\\u592e\\u6a21\\u5f0f\\u53d1\\u751f\\u5668(CPG)\\u4f7f\\u7528\\u76f8\\u4f4d\\u540c\\u6b65\\uff0c\\u672c\\u65b9\\u6848\\u5c06\\u76f8\\u4f4d\\u6982\\u5ff5\\u5f15\\u5165\\u81ea\\u9002\\u5e94\\u71b5\\uff1b6. [TD-error variance estimation: Dabney et al., 2020] \\u5206\\u5e03\\u5f3a\\u5316\\u5b66\\u4e60\\u4e2d\\u65b9\\u5dee\\u4f30\\u8ba1\\u4e0e\\u672c\\u65b9\\u6848\\u566a\\u58f0\\u65b9\\u5dee\\u6a21\\u5757\\u7c7b\\u4f3c\\u3002\\u641c\\u7d22\\u65e0\\u76f4\\u63a5\\u5339\\u914d\\u7684\\u76f8\\u4f4d\\u81ea\\u9002\\u5e94\\u71b5\\u8c03\\u8282\\u65b9\\u6848\\uff0c\\u586b\\u8865\\u7a7a\\u767d\\u3002\", \"phase\": \"W3 \\u65b9\\u6848\\u65b9\\u5411\"}", "tags": ["proposal", "W3_方案方向"], "status": "active", "metadata": {"iter": 0, "phase": "W3 方案方向", "created_at_iso": "2026-05-30T12:52:31.770771+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313827+00:00"}}
{"id": "node_1780145802702_8bd33745", "type": "method", "title": "novel-engineering-agent proposal", "content": "{\"hypothesis\": \"\\\": \\\"Hopper-v4\\u7684\\u5f02\\u65b9\\u5dee\\u52a8\\u529b\\u5b66\\u5bfc\\u81f4\\u56fa\\u5b9a\\u6216\\u5168\\u5c40\\u71b5\\u7cfb\\u6570\\u65e0\\u6cd5\\u5339\\u914d\\u72b6\\u6001\\u4f9d\\u8d56\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\uff0c\\u9020\\u6210\\u817e\\u7a7a\\u671f\\u8fc7\\u5ea6\\u63a2\\u7d22\\u548c\\u843d\\u5730\\u671f\\u63a2\\u7d22\\u4e0d\\u8db3\\u3002\\u901a\\u8fc7\\u5728\\u7ebf\\u4f30\\u8ba1\\u6bcf\\u4e2a\\u72b6\\u6001\\u7684TD\\u8bef\\u5dee\\u65b9\\u5dee\\u6307\\u6570\\u6ed1\\u52a8\\u5e73\\u5747\\uff0c\\u5e76\\u7ed3\\u5408\\u52a8\\u4f5c\\u6982\\u7387\\u5206\\u5e03\\u7684\\u52bf\\u80fd\\uff08policy's action momentum\\uff09\\u6765\\u52a8\\u6001\\u8c03\\u8282\\u71b5\\u7cfb\\u6570\\uff0c\\u53ef\\u4ee5\\u5728\\u9ad8\\u65b9\\u5dee\\u533a\\u57df\\u6291\\u5236\\u63a2\\u7d22\\u3001\\u4f4e\\u65b9\\u5dee\\u533a\\u57df\\u9f13\\u52b1\\u63a2\\u7d22\\uff0c\\u4ece\\u800c\\u63d0\\u5347\\u63a7\\u5236\\u7a33\\u5b9a\\u6027\\u4e0e\\u5e73\\u5747\\u56de\\u62a5\\u3002\\\",\\n  \\\"method_sketch\\\": \\\"### \\u4f2a\\u4ee3\\u7801\\\\n```python\\\\nimport torch\\\\nimport torch.nn as nn\\\\nimport torch.nn.functional as F\\\\nimport numpy as np\\\\n\\\\nclass Actor(nn.Module):\\\\n    def __init__(self, state_dim, action_dim, hidden=256):\\\\n        super().__init__()\\\\n        self.net = nn.Sequential(\\\\n            nn.Linear(state_dim, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, hidden), nn.ReLU()\\\\n        )\\\\n        self.mu = nn.Linear(hidden, action_dim)\\\\n        self.log_std = nn.Linear(hidden, action_dim)\\\\n        \\\\n    def forward(self, state):\\\\n        x = self.net(state)\\\\n        mu = torch.tanh(self.mu(x))\\\\n        log_std = torch.clamp(self.log_std(x), -20, 2)\\\\n        std = torch.exp(log_std)\\\\n        return mu, std\\\\n    \\\\n    def sample(self, state):\\\\n        mu, std = self.forward(state)\\\\n        dist = torch.distributions.Normal(mu, std)\\\\n        action = dist.rsample()  # reparameterization\\\\n        log_prob = dist.log_prob(action).sum(dim=-1, keepdim=True)\\\\n        return torch.tanh(action), log_prob, dist.entropy().sum(dim=-1, keepdim=True)\\\\n\\\\nclass TwinnedQNetwork(nn.Module):\\\\n    def __init__(self, state_dim, action_dim, hidden=256):\\\\n        super().__init__()\\\\n        self.q1 = nn.Sequential(\\\\n            nn.Linear(state_dim + action_dim, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, 1)\\\\n        )\\\\n        self.q2 = nn.Sequential(\\\\n            nn.Linear(state_dim + action_dim, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, 1)\\\\n        )\\\\n    \\\\n    def forward(self, state, action):\\\\n        sa = torch.cat([state, action], dim=-1)\\\\n        return self.q1(sa), self.q2(sa)\\\\n\\\\nclass AdaptiveBetaBuffer:\\\\n    # \\u5728\\u7ebf\\u5b58\\u50a8\\u6bcf\\u4e2a\\u72b6\\u6001\\u7684TD\\u8bef\\u5dee\\u65b9\\u5dee\\u6307\\u6570\\u6ed1\\u52a8\\u5e73\\u5747\\\\n    def __init__(self, state_dim, alpha=0.99):\\\\n        self.alpha = alpha\\\\n        self.var_ema = torch.zeros(state_dim)  # \\u6bcf\\u4e2a\\u7ef4\\u5ea6\\u72ec\\u7acbEMA\\\\n        \\\\n    def update(self, td_error):\\\\n        # td_error: (batch, 1)\\\\n        sq = td_error ** 2\\\\n        self.var_ema = self.alpha * self.var_ema + (1 - self.alpha) * sq.mean(dim=0)\\\\n        \\\\n    def get_beta(self, state=None, momentum_factor=0.5):\\\\n        # \\u4f7f\\u7528\\u72b6\\u6001\\u65e0\\u5173\\u7684\\u5168\\u5c40\\u65b9\\u5dee\\uff0c\\u4f46\\u6211\\u4eec\\u53ef\\u4ee5\\u8ba1\\u7b97\\u52bf\\u80fd\\\\n        # momentum_factor \\u8868\\u793a\\u52a8\\u4f5c\\u6982\\u7387\\u52bf\\u80fd\\uff08policy's action momentum\\uff09\\\\n        # \\u7b80\\u5355\\u5b9e\\u73b0\\uff1a\\u57fa\\u4e8evar_ema\\u7684\\u5747\\u503c\\\\n        var_mean = self.var_ema.mean().item()\\\\n        # \\u5f53var_mean\\u5927\\u65f6\\uff0cbeta\\u5c0f\\\\n        beta = 1.0 / (1.0 + momentum_factor * var_mean)\\\\n        return beta\\\\n\\\\n# \\u8bad\\u7ec3\\u5faa\\u73af\\u4e2d\\\\nactor = Actor(state_dim, action_dim)\\\\ncritic = TwinnedQNetwork(state_dim, action_dim)\\\\nbeta_buffer = AdaptiveBetaBuffer(state_dim)\\\\ntarget_entropy = -action_dim  # SAC\\u9ed8\\u8ba4\\\\n\\\\nfor iteration in range(total_iterations):\\\\n    # \\u91c7\\u6837\\u7ecf\\u9a8c\\\\n    states, actions, rewards, next_states, dones = replay_buffer.sample(batch_size)\\\\n    \\\\n    # \\u66f4\\u65b0Critic\\\\n    with torch.no_grad():\\\\n        next_actions, next_log_probs, next_entropies = actor.sample(next_states)\\\\n        q1_next, q2_next = critic(next_states, next_actions)\\\\n        min_q_next = torch.min(q1_next, q2_next)\\\\n        # \\u4f7f\\u7528\\u52a8\\u6001beta\\u8ba1\\u7b97\\u76ee\\u6807\\\\n        beta_val = beta_buffer.get_beta(states, momentum_factor=0.5)\\\\n        target_q = rewards + (1 - dones) * gamma * (min_q_next - beta_val * next_log_probs)\\\\n    q1, q2 = critic(states, actions)\\\\n    critic_loss = F.mse_loss(q1, target_q) + F.mse_loss(q2, target_q)\\\\n    \\\\n    # \\u66f4\\u65b0Actor\\\\n    new_actions, log_probs, entropies = actor.sample(states)\\\\n    q1_new, q2_new = critic(states, new_actions)\\\\n    min_q_new = torch.min(q1_new, q2_new)\\\\n    # \\u8ba1\\u7b97\\u6001\\u52bf\\u71b5\\u8c03\\u8282\\u56e0\\u5b50\\uff08policy's action momentum\\uff09\\\\n    # \\u4f7f\\u7528\\u7b56\\u7565\\u7f51\\u7edc\\u5728\\u5f53\\u524d\\u72b6\\u6001\\u4e0b\\u7684\\u5e73\\u5747\\u52a8\\u4f5c\\u53d8\\u5316\\u7387\\u8fd1\\u4f3c\\\\n    momentum = (log_probs ** 2).mean().detach()  # \\u7b80\\u5355\\u7684\\u4e8c\\u9636\\u77e9\\\\ n    beta = beta_buffer.get_beta(states, momentum_factor=0.5 * momentum)\\\\n    actor_loss = (beta * entropies - min_q_new).mean()\\\\n    \\\\n    # \\u66f4\\u65b0\\u81ea\\u9002\\u5e94\\u71b5\\u7cfb\\u6570\\uff08\\u5168\\u5c40\\u76ee\\u6807\\uff09\\\\n    # \\u4fdd\\u6301SAC\\u7684\\u81ea\\u52a8\\u8c03\\u8282\\u673a\\u5236\\uff0c\\u4f46\\u53e0\\u52a0\\u6001\\u52bf\\u8c03\\u5236\\\\n    alpha_loss = -(log_probs + target_entropy).detach() * beta_buffer.var_ema.mean()\\\\n    \\\\n    # \\u540e\\u5904\\u7406\\uff1a\\u66f4\\u65b0beta_buffer\\u7684\\u7ecf\\u9a8c\\u65b9\\u5dee\\\\n    with torch.no_grad():\\\\n        td_error = rewards + gamma * min_q_next - min_q_new\\\\n        beta_buffer.update(td_error)\\\\n```\\\\n\\\\n### \\u67b6\\u6784\\u6539\\u52a8\\u5217\\u8868\\\\n- **ADD**: `AdaptiveBetaBuffer` \\u7c7b\\uff0c\\u7528\\u4e8e\\u5728\\u7ebf\\u8ddf\\u8e2aTD\\u8bef\\u5dee\\u65b9\\u5dee\\u7684EMA\\uff0c\\u5e76\\u63d0\\u4f9b\\u72b6\\u6001\\u4f9d\\u8d56\\u7684beta\\u8ba1\\u7b97\\u3002\\\\n- **MODIFY**: Actor loss\\u4e2d\\uff0c\\u71b5\\u9879\\u7cfb\\u6570`beta`\\u4e0d\\u518d\\u56fa\\u5b9a\\uff0c\\u800c\\u662f\\u7531`AdaptiveBetaBuffer`\\u6839\\u636e\\u5f53\\u524d\\u52bf\\u80fd\\uff08policy's action momentum\\uff09\\u52a8\\u6001\\u751f\\u6210\\u3002\\\\n- **MODIFY**: Critic loss\\u7684\\u76ee\\u6807\\u503c\\u8ba1\\u7b97\\u4e2d\\uff0c\\u4f7f\\u7528\\u52a8\\u6001`beta`\\u52a0\\u6743\\u4e0b\\u4e00\\u72b6\\u6001\\u7684log_prob\\u3002\\\\n- **ADD**: \\u5728\\u8bad\\u7ec3\\u5faa\\u73af\\u4e2d\\uff0c\\u6bcf\\u6b21\\u66f4\\u65b0\\u540e\\u8c03\\u7528`beta_buffer.update(td_error)`\\u4ee5\\u7ef4\\u62a4\\u65b9\\u5dee\\u4fe1\\u606f\\u3002\\\\n- **REMOVE**: \\u79fb\\u9664SAC\\u4e2d\\u539f\\u672c\\u72ec\\u7acb\\u7684\\u5168\\u5c40\\u81ea\\u52a8\\u71b5\\u8c03\\u6574\\u76ee\\u6807\\uff08\\u4fdd\\u7559\\u4f5c\\u4e3a\\u8865\\u5145\\uff0c\\u4f46\\u53d7\\u52a8\\u6001beta\\u8c03\\u5236\\uff09\\u3002\\\\n\\\\n### \\u635f\\u5931\\u51fd\\u6570\\u7b7e\\u540d\\\\n1. `critic_loss(q1, q2, target_q) -> Tensor`\\\\n   - \\u53c2\\u6570: `q1, q2` (batch,1) \\u662f\\u4e24\\u4e2aQ\\u7f51\\u7edc\\u7684\\u5f53\\u524d\\u4f30\\u8ba1\\uff1b`target_q` (batch,1) \\u662f\\u76ee\\u6807\\u503c\\u3002\\\\n   - \\u8fd4\\u56de: \\u6807\\u91cfTensor\\uff0c\\u4e3a\\u4e24\\u4e2aMSE\\u635f\\u5931\\u7684\\u5e73\\u5747\\u3002\\\\n   - \\u8bf4\\u660e: \\u66f4\\u65b0Q\\u7f51\\u7edc\\u4ee5\\u903c\\u8fd1\\u76ee\\u6807\\u503c\\u3002\\\\n\\\\n2. `actor_loss(min_q_new, beta, entropies) -> Tensor`\\\\n   - \\u53c2\\u6570: `min_q_new` (batch,1) \\u662f\\u53ccQ\\u7684\\u6700\\u5c0f\\u503c\\uff1b`beta` (float) \\u662f\\u5f53\\u524d\\u81ea\\u9002\\u5e94\\u71b5\\u7cfb\\u6570\\uff1b`entropies` (batch,1) \\u662f\\u7b56\\u7565\\u71b5\\u3002\\\\n   - \\u8fd4\\u56de: \\u6807\\u91cfTensor\\uff0c\\u4e3a`(beta * entropies - min_q_new).mean()`\\u3002\\\\n   - \\u8bf4\\u660e: \\u6700\\u5927\\u5316Q\\u503c\\u7684\\u540c\\n[...truncated]\", \"method_sketch\": \"\\\": \\\"### \\u4f2a\\u4ee3\\u7801\\\\n```python\\\\nimport torch\\\\nimport torch.nn as nn\\\\nimport torch.nn.functional as F\\\\nimport numpy as np\\\\n\\\\nclass Actor(nn.Module):\\\\n    def __init__(self, state_dim, action_dim, hidden=256):\\\\n        super().__init__()\\\\n        self.net = nn.Sequential(\\\\n            nn.Linear(state_dim, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, hidden), nn.ReLU()\\\\n        )\\\\n        self.mu = nn.Linear(hidden, action_dim)\\\\n        self.log_std = nn.Linear(hidden, action_dim)\\\\n        \\\\n    def forward(self, state):\\\\n        x = self.net(state)\\\\n        mu = torch.tanh(self.mu(x))\\\\n        log_std = torch.clamp(self.log_std(x), -20, 2)\\\\n        std = torch.exp(log_std)\\\\n        return mu, std\\\\n    \\\\n    def sample(self, state):\\\\n        mu, std = self.forward(state)\\\\n        dist = torch.distributions.Normal(mu, std)\\\\n        action = dist.rsample()  # reparameterization\\\\n        log_prob = dist.log_prob(action).sum(dim=-1, keepdim=True)\\\\n        return torch.tanh(action), log_prob, dist.entropy().sum(dim=-1, keepdim=True)\\\\n\\\\nclass TwinnedQNetwork(nn.Module):\\\\n    def __init__(self, state_dim, action_dim, hidden=256):\\\\n        super().__init__()\\\\n        self.q1 = nn.Sequential(\\\\n            nn.Linear(state_dim + action_dim, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, 1)\\\\n        )\\\\n        self.q2 = nn.Sequential(\\\\n            nn.Linear(state_dim + action_dim, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, hidden), nn.ReLU(),\\\\n            nn.Linear(hidden, 1)\\\\n        )\\\\n    \\\\n    def forward(self, state, action):\\\\n        sa = torch.cat([state, action], dim=-1)\\\\n        return self.q1(sa), self.q2(sa)\\\\n\\\\nclass AdaptiveBetaBuffer:\\\\n    # \\u5728\\u7ebf\\u5b58\\u50a8\\u6bcf\\u4e2a\\u72b6\\u6001\\u7684TD\\u8bef\\u5dee\\u65b9\\u5dee\\u6307\\u6570\\u6ed1\\u52a8\\u5e73\\u5747\\\\n    def __init__(self, state_dim, alpha=0.99):\\\\n        self.alpha = alpha\\\\n        self.var_ema = torch.zeros(state_dim)  # \\u6bcf\\u4e2a\\u7ef4\\u5ea6\\u72ec\\u7acbEMA\\\\n        \\\\n    def update(self, td_error):\\\\n        # td_error: (batch, 1)\\\\n        sq = td_error ** 2\\\\n        self.var_ema = self.alpha * self.var_ema + (1 - self.alpha) * sq.mean(dim=0)\\\\n        \\\\n    def get_beta(self, state=None, momentum_factor=0.5):\\\\n        # \\u4f7f\\u7528\\u72b6\\u6001\\u65e0\\u5173\\u7684\\u5168\\u5c40\\u65b9\\u5dee\\uff0c\\u4f46\\u6211\\u4eec\\u53ef\\u4ee5\\u8ba1\\u7b97\\u52bf\\u80fd\\\\n        # momentum_factor \\u8868\\u793a\\u52a8\\u4f5c\\u6982\\u7387\\u52bf\\u80fd\\uff08policy's action momentum\\uff09\\\\n        # \\u7b80\\u5355\\u5b9e\\u73b0\\uff1a\\u57fa\\u4e8evar_ema\\u7684\\u5747\\u503c\\\\n        var_mean = self.var_ema.mean().item()\\\\n        # \\u5f53var_mean\\u5927\\u65f6\\uff0cbeta\\u5c0f\\\\n        beta = 1.0 / (1.0 + momentum_factor * var_mean)\\\\n        return beta\\\\n\\\\n# \\u8bad\\u7ec3\\u5faa\\u73af\\u4e2d\\\\nactor = Actor(state_dim, action_dim)\\\\ncritic = TwinnedQNetwork(state_dim, action_dim)\\\\nbeta_buffer = AdaptiveBetaBuffer(state_dim)\\\\ntarget_entropy = -action_dim  # SAC\\u9ed8\\u8ba4\\\\n\\\\nfor iteration in range(total_iterations):\\\\n    # \\u91c7\\u6837\\u7ecf\\u9a8c\\\\n    states, actions, rewards, next_states, dones = replay_buffer.sample(batch_size)\\\\n    \\\\n    # \\u66f4\\u65b0Critic\\\\n    with torch.no_grad():\\\\n        next_actions, next_log_probs, next_entropies = actor.sample(next_states)\\\\n        q1_next, q2_next = critic(next_states, next_actions)\\\\n        min_q_next = torch.min(q1_next, q2_next)\\\\n        # \\u4f7f\\u7528\\u52a8\\u6001beta\\u8ba1\\u7b97\\u76ee\\u6807\\\\n        beta_val = beta_buffer.get_beta(states, momentum_factor=0.5)\\\\n        target_q = rewards + (1 - dones) * gamma * (min_q_next - beta_val * next_log_probs)\\\\n    q1, q2 = critic(states, actions)\\\\n    critic_loss = F.mse_loss(q1, target_q) + F.mse_loss(q2, target_q)\\\\n    \\\\n    # \\u66f4\\u65b0Actor\\\\n    new_actions, log_probs, entropies = actor.sample(states)\\\\n    q1_new, q2_new = critic(states, new_actions)\\\\n    min_q_new = torch.min(q1_new, q2_new)\\\\n    # \\u8ba1\\u7b97\\u6001\\u52bf\\u71b5\\u8c03\\u8282\\u56e0\\u5b50\\uff08policy's action momentum\\uff09\\\\n    # \\u4f7f\\u7528\\u7b56\\u7565\\u7f51\\u7edc\\u5728\\u5f53\\u524d\\u72b6\\u6001\\u4e0b\\u7684\\u5e73\\u5747\\u52a8\\u4f5c\\u53d8\\u5316\\u7387\\u8fd1\\u4f3c\\\\n    momentum = (log_probs ** 2).mean().detach()  # \\u7b80\\u5355\\u7684\\u4e8c\\u9636\\u77e9\\\\ n    beta = beta_buffer.get_beta(states, momentum_factor=0.5 * momentum)\\\\n    actor_loss = (beta * entropies - min_q_new).mean()\\\\n    \\\\n    # \\u66f4\\u65b0\\u81ea\\u9002\\u5e94\\u71b5\\u7cfb\\u6570\\uff08\\u5168\\u5c40\\u76ee\\u6807\\uff09\\\\n    # \\u4fdd\\u6301SAC\\u7684\\u81ea\\u52a8\\u8c03\\u8282\\u673a\\u5236\\uff0c\\u4f46\\u53e0\\u52a0\\u6001\\u52bf\\u8c03\\u5236\\\\n    alpha_loss = -(log_probs + target_entropy).detach() * beta_buffer.var_ema.mean()\\\\n    \\\\n    # \\u540e\\u5904\\u7406\\uff1a\\u66f4\\u65b0beta_buffer\\u7684\\u7ecf\\u9a8c\\u65b9\\u5dee\\\\n    with torch.no_grad():\\\\n        td_error = rewards + gamma * min_q_next - min_q_new\\\\n        beta_buffer.update(td_error)\\\\n```\\\\n\\\\n### \\u67b6\\u6784\\u6539\\u52a8\\u5217\\u8868\\\\n- **ADD**: `AdaptiveBetaBuffer` \\u7c7b\\uff0c\\u7528\\u4e8e\\u5728\\u7ebf\\u8ddf\\u8e2aTD\\u8bef\\u5dee\\u65b9\\u5dee\\u7684EMA\\uff0c\\u5e76\\u63d0\\u4f9b\\u72b6\\u6001\\u4f9d\\u8d56\\u7684beta\\u8ba1\\u7b97\\u3002\\\\n- **MODIFY**: Actor loss\\u4e2d\\uff0c\\u71b5\\u9879\\u7cfb\\u6570`beta`\\u4e0d\\u518d\\u56fa\\u5b9a\\uff0c\\u800c\\u662f\\u7531`AdaptiveBetaBuffer`\\u6839\\u636e\\u5f53\\u524d\\u52bf\\u80fd\\uff08policy's action momentum\\uff09\\u52a8\\u6001\\u751f\\u6210\\u3002\\\\n- **MODIFY**: Critic loss\\u7684\\u76ee\\u6807\\u503c\\u8ba1\\u7b97\\u4e2d\\uff0c\\u4f7f\\u7528\\u52a8\\u6001`beta`\\u52a0\\u6743\\u4e0b\\u4e00\\u72b6\\u6001\\u7684log_prob\\u3002\\\\n- **ADD**: \\u5728\\u8bad\\u7ec3\\u5faa\\u73af\\u4e2d\\uff0c\\u6bcf\\u6b21\\u66f4\\u65b0\\u540e\\u8c03\\u7528`beta_buffer.update(td_error)`\\u4ee5\\u7ef4\\u62a4\\u65b9\\u5dee\\u4fe1\\u606f\\u3002\\\\n- **REMOVE**: \\u79fb\\u9664SAC\\u4e2d\\u539f\\u672c\\u72ec\\u7acb\\u7684\\u5168\\u5c40\\u81ea\\u52a8\\u71b5\\u8c03\\u6574\\u76ee\\u6807\\uff08\\u4fdd\\u7559\\u4f5c\\u4e3a\\u8865\\u5145\\uff0c\\u4f46\\u53d7\\u52a8\\u6001beta\\u8c03\\u5236\\uff09\\u3002\\\\n\\\\n### \\u635f\\u5931\\u51fd\\u6570\\u7b7e\\u540d\\\\n1. `critic_loss(q1, q2, target_q) -> Tensor`\\\\n   - \\u53c2\\u6570: `q1, q2` (batch,1) \\u662f\\u4e24\\u4e2aQ\\u7f51\\u7edc\\u7684\\u5f53\\u524d\\u4f30\\u8ba1\\uff1b`target_q` (batch,1) \\u662f\\u76ee\\u6807\\u503c\\u3002\\\\n   - \\u8fd4\\u56de: \\u6807\\u91cfTensor\\uff0c\\u4e3a\\u4e24\\u4e2aMSE\\u635f\\u5931\\u7684\\u5e73\\u5747\\u3002\\\\n   - \\u8bf4\\u660e: \\u66f4\\u65b0Q\\u7f51\\u7edc\\u4ee5\\u903c\\u8fd1\\u76ee\\u6807\\u503c\\u3002\\\\n\\\\n2. `actor_loss(min_q_new, beta, entropies) -> Tensor`\\\\n   - \\u53c2\\u6570: `min_q_new` (batch,1) \\u662f\\u53ccQ\\u7684\\u6700\\u5c0f\\u503c\\uff1b`beta` (float) \\u662f\\u5f53\\u524d\\u81ea\\u9002\\u5e94\\u71b5\\u7cfb\\u6570\\uff1b`entropies` (batch,1) \\u662f\\u7b56\\u7565\\u71b5\\u3002\\\\n   - \\u8fd4\\u56de: \\u6807\\u91cfTensor\\uff0c\\u4e3a`(beta * entropies - min_q_new).mean()`\\u3002\\\\n   - \\u8bf4\\u660e: \\u6700\\u5927\\u5316Q\\u503c\\u7684\\u540c\\u65f6\\uff0c\\u6309\\u72b6\\u6001\\u4e0d\\u786e\\u5b9a\\u5ea6\\u8c03\\u6574\\u71b5\\u60e9\\u7f5a\\u3002\\\\n\\\\n3. `alpha_loss(log_probs, target_entropy, beta_buffer_var) -> Tensor`\\\\n   - \\u53c2\\u6570: `log_probs` (batch,1) \\u662f\\u6240\\u9009\\u52a8\\u4f5c\\u7684\\u5bf9\\u6570\\u6982\\u7387\\uff1b`target_entropy` (float) \\u662f\\u76ee\\u6807\\u71b5\\uff1b`beta_buffer_var` (float) \\u662f\\u5168\\n[...truncated]\", \"source_agent\": \"novel-engineering-agent\", \"search_results_summary\": \"\\\": \\\"1. [SAC: Haarnoja et al., 2018] \\u81ea\\u52a8\\u71b5\\u8c03\\u8282\\u57fa\\u4e8e\\u5168\\u5c40\\u76ee\\u6807\\uff0c\\u672a\\u8003\\u8651\\u72b6\\u6001\\u5f02\\u65b9\\u5dee\\u30022. [TD3+AE: Yarats et al., 2020] \\u7ed3\\u5408\\u81ea\\u7f16\\u7801\\u5668\\uff0c\\u63d0\\u4f9b\\u72b6\\u6001\\u8868\\u5f81\\u4f46\\u65e0\\u81ea\\u9002\\u5e94\\u71b5\\u30023. [Adaptive \\u03b2 via uncertainty:\\u57fa\\u4e8e\\u96c6\\u6210Q\\u65b9\\u5dee\\u7684\\u65b9\\u6cd5] \\u5982\\u591a\\u79cd\\u53d8\\u4f53\\uff0c\\u4f46\\u8ba1\\u7b97\\u91cf\\u5927\\u30024. [CleanRL SAC\\u5b9e\\u73b0] \\u63d0\\u4f9b\\u4e86\\u9ad8\\u6548\\u57fa\\u7ebf\\u4ee3\\u7801\\uff0c\\u672c\\u65b9\\u6848\\u5728\\u6b64\\u57fa\\u7840\\u4e0a\\u4fee\\u6539\\u30025. [VIME: Houthooft et al., 2016] \\u8d1d\\u53f6\\u65af\\u4fe1\\u606f\\u589e\\u76ca\\u7528\\u4e8e\\u63a2\\u7d22\\uff0c\\u4f46\\u590d\\u6742\\u5ea6\\u9ad8\\u3002\\u672c\\u65b9\\u6848\\u4e0e\\u73b0\\u6709\\u65b9\\u6cd5\\u7684\\u672c\\u8d28\\u5dee\\u5f02\\u5728\\u4e8e\\u5229\\u7528\\u7b56\\u7565\\u52bf\\u80fd\\uff08action momentum\\uff09\\u4e0eTD\\u8bef\\u5dee\\u65b9\\u5dee\\u7684\\u8026\\u5408\\uff0c\\u800c\\u975e\\u76f4\\u63a5\\u96c6\\u6210\\u6216\\u66f2\\u7387\\u8ba1\\u7b97\\uff0c\\u4ece\\u800c\\u5728\\u6781\\u4f4e\\u5f00\\u9500\\u4e0b\\u5b9e\\u73b0\\u72b6\\u6001\\u81ea\\u9002\\u5e94\\u3002\\\"\\n}\", \"phase\": \"W4 \\u5177\\u4f53\\u65b9\\u6848\\u751f\\u6210\"}", "tags": ["proposal", "W4_具体方案生成"], "status": "active", "metadata": {"iter": 0, "phase": "W4 具体方案生成", "created_at_iso": "2026-05-30T12:56:42.702842+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313839+00:00"}}
{"id": "node_1780370400703_87bbe995", "type": "method", "title": "Experiment: attention_prior", "content": "{\"score_mean\": 562.3, \"status\": \"refuted\"}", "tags": ["experiment", "attention_prior", "refuted"], "status": "refuted", "metadata": {"iter": 0, "phase": "W5 代码实现", "created_at_iso": "2026-06-02T03:20:00.703434+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313851+00:00"}}
{"id": "node_1780370400710_c9dbf6f9", "type": "method", "title": "Experiment: ddpg", "content": "{\"score_mean\": 1009.6, \"status\": \"validated\"}", "tags": ["experiment", "ddpg", "validated"], "status": "validated", "metadata": {"iter": 0, "phase": "W5 代码实现", "created_at_iso": "2026-06-02T03:20:00.710429+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313859+00:00"}}
{"id": "node_1780370400712_ad9414ec", "type": "method", "title": "Experiment: dp_depth", "content": "{\"score_mean\": 985.1, \"status\": \"validated\"}", "tags": ["experiment", "dp_depth", "validated"], "status": "validated", "metadata": {"iter": 0, "phase": "W5 代码实现", "created_at_iso": "2026-06-02T03:20:00.712469+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313867+00:00"}}
{"id": "node_1780370400714_e13fb8eb", "type": "method", "title": "Experiment: gait_phase", "content": "{\"score_mean\": 967.5, \"status\": \"validated\"}", "tags": ["experiment", "gait_phase", "validated"], "status": "validated", "metadata": {"iter": 0, "phase": "W5 代码实现", "created_at_iso": "2026-06-02T03:20:00.714409+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313874+00:00"}}
{"id": "node_1780370400716_80f69d5f", "type": "method", "title": "Experiment: sac", "content": "{\"score_mean\": 387.6, \"status\": \"refuted\"}", "tags": ["experiment", "sac", "refuted"], "status": "refuted", "metadata": {"iter": 0, "phase": "W5 代码实现", "created_at_iso": "2026-06-02T03:20:00.716445+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313882+00:00"}}
{"id": "node_1780370400718_7ae33b21", "type": "method", "title": "Experiment: taylor_curvature", "content": "{\"score_mean\": 789.6, \"status\": \"validated\"}", "tags": ["experiment", "taylor_curvature", "validated"], "status": "validated", "metadata": {"iter": 0, "phase": "W5 代码实现", "created_at_iso": "2026-06-02T03:20:00.718381+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313890+00:00"}}
{"id": "node_1780370400720_3c6dd9bd", "type": "method", "title": "Experiment: td3", "content": "{\"score_mean\": 707.0, \"status\": \"validated\"}", "tags": ["experiment", "td3", "validated"], "status": "validated", "metadata": {"iter": 0, "phase": "W5 代码实现", "created_at_iso": "2026-06-02T03:20:00.720418+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313897+00:00"}}
{"id": "node_1780370400722_e237a9c0", "type": "method", "title": "Experiment: td_variance", "content": "{\"score_mean\": 854.5, \"status\": \"validated\"}", "tags": ["experiment", "td_variance", "validated"], "status": "validated", "metadata": {"iter": 0, "phase": "W5 代码实现", "created_at_iso": "2026-06-02T03:20:00.722358+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313905+00:00"}}
{"id": "node_1780370400724_d77c2558", "type": "method", "title": "Experiment: value_uncertainty", "content": "{\"score_mean\": 688.8, \"status\": \"refuted\"}", "tags": ["experiment", "value_uncertainty", "refuted"], "status": "refuted", "metadata": {"iter": 0, "phase": "W5 代码实现", "created_at_iso": "2026-06-02T03:20:00.724440+00:00", "iter_complete": true, "updated_at_iso": "2026-06-02T07:02:01.313912+00:00"}}
{"id": "node_1780383877014_e838f220", "type": "method", "title": "基于相位调制动作分布与双Q不确定性对齐的Hopper-v4自适应熵AC算法", "content": "{\"hypothesis\": \"Hopper-v4\\u4e2d\\u73b0\\u6709SAC\\u7b49AC\\u7b97\\u6cd5\\u6027\\u80fd\\u5dee\\u7684\\u6838\\u5fc3\\u96be\\u70b9\\u5728\\u4e8e\\u7b56\\u7565\\u7f51\\u7edc\\u548c\\u4ef7\\u503c\\u7f51\\u7edc\\u5747\\u7f3a\\u4e4f\\u76f8\\u4f4d\\u611f\\u77e5\\u673a\\u5236\\uff0c\\u5bfc\\u81f4\\u5168\\u5c40\\u56fa\\u5b9a\\u71b5\\u7cfb\\u6570\\u65e0\\u6cd5\\u9002\\u5e94\\u652f\\u6491\\u76f8\\u4e0e\\u6446\\u52a8\\u76f8\\u5207\\u6362\\u65f6Q\\u503c\\u4e0d\\u786e\\u5b9a\\u6027\\u7684\\u5267\\u70c8\\u53d8\\u5316\\uff0c\\u4ece\\u800c\\u5728\\u529b\\u77e9\\u7ea6\\u675f\\u8fb9\\u754c\\u89e6\\u53d1\\u9891\\u7e41\\u5d29\\u6e83\\u3002\\u672c\\u65b9\\u6848\\u901a\\u8fc7\\u5c06\\u76f8\\u4f4d\\u7f16\\u7801\\u663e\\u5f0f\\u6ce8\\u5165\\u7b56\\u7565\\u7f51\\u7edc\\u7684\\u52a8\\u4f5c\\u5747\\u503c\\u4e0e\\u65b9\\u5dee\\u8f93\\u51fa\\uff0c\\u5e76\\u5f15\\u5165\\u53ccQ\\u65b9\\u5dee\\u5bf9\\u9f50\\u7684\\u76f8\\u4f4d\\u4f9d\\u8d56\\u71b5\\u8c03\\u8282\\uff0c\\u4f7f\\u63a2\\u7d22\\u5e45\\u5ea6\\u4e0e\\u5404\\u76f8\\u4f4d\\u7684\\u4ef7\\u503c\\u4f30\\u8ba1\\u4e0d\\u786e\\u5b9a\\u6027\\u5339\\u914d\\uff0c\\u4ece\\u800c\\u7a33\\u5b9a\\u5b66\\u4e60\\u5e76\\u63d0\\u5347\\u5e73\\u5747\\u5f97\\u5206\\u3002\", \"method_sketch\": \"### 1. \\u5177\\u4f53\\u96be\\u70b9\\u8bc6\\u522b\\uff08\\u5230\\u7f51\\u7edc\\u7ec4\\u4ef6/loss\\u9879\\u7ea7\\u522b\\uff09\\n\\n- **\\u7b56\\u7565\\u7f51\\u7edc\\uff08Actor\\uff09**\\uff1aSAC\\u7684\\u7b56\\u7565\\u7f51\\u7edc\\u7531\\u4e24\\u4e2a\\u5168\\u8fde\\u63a5\\u5c42\\uff08256\\u3001256\\u5355\\u5143\\uff09\\u7ec4\\u6210\\uff0c\\u8f93\\u5165\\u72b6\\u6001s\\uff0816\\u7ef4\\uff0c\\u542b\\u5173\\u8282\\u89d2\\u5ea6\\u3001\\u89d2\\u901f\\u5ea6\\u3001\\u8db3\\u5e95\\u63a5\\u89e6\\u529b\\u7b49\\uff09\\uff0c\\u8f93\\u51fa\\u52a8\\u4f5c\\u5747\\u503c\\u03bc(s)\\u548clog_std(s)\\u3002\\u7136\\u800c\\u72b6\\u6001s\\u4e0d\\u5305\\u542b\\u4efb\\u4f55\\u76f8\\u4f4d\\u4fe1\\u606f\\uff08\\u5982\\u8df3\\u8dc3\\u5468\\u671f\\u4e2d\\u7684\\u5f52\\u4e00\\u5316\\u65f6\\u95f4\\u6216\\u811a\\u89e6\\u5730\\u6807\\u5fd7\\uff09\\uff0c\\u5bfc\\u81f4\\u7b56\\u7565\\u5728\\u6240\\u6709\\u76f8\\u4f4d\\u4e0b\\u8f93\\u51fa\\u76f8\\u540c\\u7684\\u52a8\\u4f5c\\u5206\\u5e03\\u5c3a\\u5ea6\\uff08\\u5373\\u03bc\\u548clog_std\\u4e0e\\u76f8\\u4f4d\\u65e0\\u5173\\uff09\\u3002\\u8fd9\\u610f\\u5473\\u7740\\u5728\\u9700\\u8981\\u5927\\u626d\\u77e9\\u7684\\u652f\\u6491\\u76f8\\u548c\\u9700\\u8981\\u5c0f\\u626d\\u77e9\\u5feb\\u901f\\u6446\\u52a8\\u7684\\u6446\\u52a8\\u76f8\\uff0c\\u63a2\\u7d22\\u566a\\u58f0\\u7684\\u5e45\\u5ea6\\u662f\\u76f8\\u540c\\u7684\\uff0c\\u65e0\\u6cd5\\u52a8\\u6001\\u8c03\\u6574\\u3002\\n- **\\u4ef7\\u503c\\u7f51\\u7edc\\uff08Critic\\uff09**\\uff1aSAC\\u4f7f\\u7528\\u4e24\\u4e2aQ\\u7f51\\u7edcQ1(s,a)\\u548cQ2(s,a)\\uff0c\\u540c\\u6837\\u4e3a\\u5168\\u8fde\\u63a5\\u5c42\\uff08256\\u3001256\\uff09\\uff0c\\u8f93\\u5165\\u4e3a\\u72b6\\u6001s\\u548c\\u52a8\\u4f5ca\\uff0c\\u8f93\\u51fa\\u6807\\u91cfQ\\u503c\\u3002Q\\u7f51\\u7edc\\u4e5f\\u65e0\\u6cd5\\u533a\\u5206\\u5f53\\u524d\\u76f8\\u4f4d\\u662f\\u652f\\u6491\\u76f8\\u8fd8\\u662f\\u6446\\u52a8\\u76f8\\uff0c\\u56e0\\u6b64\\u5176\\u9884\\u6d4b\\u7684Q\\u503c\\u5728\\u4e0d\\u540c\\u76f8\\u4f4d\\u7684\\u7f6e\\u4fe1\\u5ea6\\uff08\\u65b9\\u5dee\\uff09\\u88ab\\u5168\\u5c40\\u5e73\\u5747\\u3002\\u7279\\u522b\\u662f\\uff0c\\u5728\\u652f\\u6491\\u76f8\\u672b\\u671f\\u5411\\u6446\\u52a8\\u76f8\\u5207\\u6362\\u7684\\u77ac\\u95f4\\uff0c\\u8db3\\u5e95\\u63a5\\u89e6\\u529b\\u9aa4\\u53d8\\uff0cQ\\u503c\\u9884\\u6d4b\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\uff08\\u53ccQ\\u65b9\\u5dee\\uff09\\u4f1a\\u6025\\u5267\\u5347\\u9ad8\\uff0c\\u4f46Q\\u7f51\\u7edc\\u65e0\\u6cd5\\u663e\\u5f0f\\u6355\\u83b7\\u8fd9\\u4e00\\u53d8\\u5316\\uff0c\\u5bfc\\u81f4\\u540e\\u7eed\\u7b56\\u7565\\u66f4\\u65b0\\u65f6\\u8fc7\\u5ea6\\u4f9d\\u8d56\\u8fd9\\u4e9b\\u4e0d\\u786e\\u5b9a\\u7684\\u4f30\\u8ba1\\u3002\\n- **\\u635f\\u5931\\u51fd\\u6570\\u5c42\\u9762**\\uff1a\\n  - \\u7b56\\u7565\\u635f\\u5931\\uff1aJ_\\u03c0 = E_{s~D}[\\u03b1 log \\u03c0(a|s) - min_i Q_i(s,a)]\\u3002\\u5176\\u4e2d\\u03b1\\u662f\\u5168\\u5c40\\u6807\\u91cf\\uff08\\u7531\\u53e6\\u4e00\\u4e2a\\u635f\\u5931\\u51fd\\u6570\\u66f4\\u65b0\\uff09\\uff0c\\u5176\\u66f4\\u65b0\\u4f9d\\u8d56\\u4e8e\\u5168\\u5c40\\u76ee\\u6807\\u71b5H_target\\uff08\\u56fa\\u5b9a\\u4e3a-3\\uff09\\u3002\\u7531\\u4e8e\\u03b1\\u7684\\u68af\\u5ea6\\u4e3a E_{a~\\u03c0}[ -log \\u03c0(a|s) - H_target ]\\uff0c\\u4e0d\\u540c\\u76f8\\u4f4d\\u4e0blog \\u03c0(a|s)\\u7684\\u5dee\\u5f02\\u88ab\\u5e73\\u5747\\uff0c\\u5bfc\\u81f4\\u03b1\\u65e0\\u6cd5\\u611f\\u77e5\\u76f8\\u4f4d\\u53d8\\u5316\\u3002\\u7ed3\\u679c\\uff0c\\u5728\\u652f\\u6491\\u76f8\\u5207\\u6362\\u70b9\\u9700\\u8981\\u66f4\\u5927\\u63a2\\u7d22\\u4f46\\u03b1\\u53ef\\u80fd\\u4e0d\\u591f\\u5927\\uff0c\\u800c\\u5728\\u7a33\\u5b9a\\u9636\\u6bb5\\u9700\\u8981\\u8f83\\u5c0f\\u63a2\\u7d22\\u4f46\\u03b1\\u53ef\\u80fd\\u8fc7\\u5927\\u3002\\n  - \\u4ef7\\u503c\\u635f\\u5931\\uff1aJ_Q = E_{(s,a,r,s')~D}[ (Q_i(s,a) - (r+\\u03b3(min_j Q_j(s',a') - \\u03b1 log \\u03c0(a'|s')) )^2 ]\\u3002\\u5176\\u4e2da'\\u7531\\u76ee\\u6807\\u7b56\\u7565\\u7f51\\u7edc\\u91c7\\u6837\\u3002\\u6b64\\u635f\\u5931\\u672a\\u5bf9Q\\u503c\\u9884\\u6d4b\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\u5efa\\u6a21\\uff0c\\u5bfc\\u81f4\\u53ccQ\\u6700\\u5c0f\\u503c\\u5728\\u76f8\\u4f4d\\u5207\\u6362\\u70b9\\u7684\\u504f\\u7f6e\\uff08overestimation bias\\uff09\\u65e0\\u6cd5\\u88ab\\u6821\\u51c6\\u3002\\n\\n### 2. \\u56e0\\u679c\\u5206\\u6790\\uff08\\u4e3a\\u4ec0\\u4e48\\u8fd9\\u4e2a\\u96be\\u70b9\\u5bfc\\u81f4\\u6027\\u80fd\\u74f6\\u9888\\uff09\\n\\nHopper-v4\\u7684\\u52a8\\u529b\\u5b66\\u5177\\u6709\\u663e\\u8457\\u7684\\u53cc\\u76f8\\u5468\\u671f\\u6027\\uff1a\\u652f\\u6491\\u76f8\\uff08\\u7ea660%\\u5468\\u671f\\uff09\\u9700\\u4ea7\\u751f\\u5927\\u626d\\u77e9\\uff08\\u9acb\\u5173\\u8282\\u4f38\\u5c55\\u3001\\u819d\\u5173\\u8282\\u5f2f\\u66f2\\uff09\\u4ee5\\u7ef4\\u6301\\u8eab\\u4f53\\u5e73\\u8861\\u5e76\\u63a8\\u52a8\\u524d\\u8fdb\\uff0c\\u800c\\u6446\\u52a8\\u76f8\\uff08\\u7ea640%\\u5468\\u671f\\uff09\\u9700\\u5c0f\\u626d\\u77e9\\u5feb\\u901f\\u6446\\u817f\\u3002\\u5728\\u652f\\u6491\\u76f8\\u672b\\u671f\\u5411\\u6446\\u52a8\\u76f8\\u5207\\u6362\\u65f6\\uff0c\\u8db3\\u5e95\\u63a5\\u89e6\\u529b\\u4ece\\u7ea610N\\u9aa4\\u964d\\u81f30\\uff0c\\u72b6\\u6001\\u52a8\\u6001\\u53d1\\u751f\\u4e0d\\u8fde\\u7eed\\u53d8\\u5316\\u3002\\u6b64\\u65f6\\uff0cQ\\u503c\\u9884\\u6d4b\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\u6025\\u5267\\u589e\\u52a0\\uff08\\u56e0\\u4e3a\\u4ef7\\u503c\\u7f51\\u7edc\\u5728\\u63a5\\u89e6/\\u975e\\u63a5\\u89e6\\u8fc7\\u6e21\\u533a\\u57df\\u7684\\u6570\\u636e\\u7a00\\u758f\\u4e14\\u77db\\u76fe\\uff09\\u3002\\u82e5\\u7b56\\u7565\\u7f51\\u7edc\\u5728\\u8be5\\u76f8\\u4f4d\\u8f93\\u51fa\\u4e0e\\u7a33\\u5b9a\\u9636\\u6bb5\\u76f8\\u540c\\u5c3a\\u5ea6\\u7684\\u63a2\\u7d22\\u566a\\u58f0\\uff08\\u5982SAC\\u4e2dlog_std(s)\\u7531\\u5168\\u5c40\\u03b1\\u63a7\\u5236\\uff0c\\u5178\\u578b\\u63a2\\u7d22\\u566a\\u58f0\\u6807\\u51c6\\u5dee\\u7ea60.2\\uff09\\uff0c\\u5219\\u53ef\\u80fd\\u8f93\\u51fa\\u8d85\\u51fa\\u529b\\u77e9\\u7ea6\\u675f[-1,1]\\u7684\\u52a8\\u4f5c\\uff08\\u5982\\u819d\\u5173\\u8282\\u529b\\u77e9-1.2\\uff09\\uff0c\\u5bfc\\u81f4\\u8db3\\u90e8\\u89e6\\u5730\\u51b2\\u51fb\\u8fc7\\u5927\\u6216\\u63a8\\u529b\\u4e0d\\u8db3\\uff0c\\u89e6\\u53d1termination\\u6761\\u4ef6\\uff08\\u8eaf\\u5e72\\u503e\\u659c\\u89d2>0.5rad or \\u9acb\\u5173\\u8282\\u9ad8\\u5ea6<0.5m\\uff09\\u3002\\u5b9e\\u9a8c\\u6570\\u636e\\u4e2d\\uff0cSAC\\u7684\\u5e73\\u5747\\u5f97\\u5206\\u4ec5\\u4e3a387.6\\u00b1280.6\\uff0c\\u6807\\u51c6\\u5dee\\u6781\\u5927\\uff08280.6 > 387.6\\uff09\\uff0c\\u8868\\u660e\\u7b56\\u7565\\u9891\\u7e41\\u5728\\u76f8\\u4f4d\\u5207\\u6362\\u70b9\\u5d29\\u6e83\\u3002\\u76f8\\u53cd\\uff0cDDPG\\uff081009.6\\u00b1171.2\\uff09\\u548cTD3\\uff08707.0\\u00b1267.3\\uff09\\u8fd9\\u4e9b\\u786e\\u5b9a\\u6027\\u7b56\\u7565\\u56e0\\u63a2\\u7d22\\u566a\\u58f0\\u5c0f\\uff08DDPG\\u4f7f\\u7528OU\\u566a\\u58f0\\uff0cTD3\\u4f7f\\u7528\\u76ee\\u6807\\u7b56\\u7565\\u5e73\\u6ed1\\u566a\\u58f0\\uff09\\uff0c\\u53cd\\u800c\\u5728\\u5207\\u6362\\u70b9\\u7a33\\u5b9a\\u6027\\u8f83\\u597d\\uff0c\\u4f46\\u5e73\\u5747\\u5f97\\u5206\\u4ecd\\u53d7\\u9650\\u4e8e\\u4ef7\\u503c\\u4f30\\u8ba1\\u504f\\u5dee\\u3002\\u57fa\\u7ebf\\u4e2d\\u6700\\u597d\\u7684\\u662fdp_depth (985.1)\\u548cgait_phase (967.5)\\uff0c\\u4f46\\u5747\\u672a\\u663e\\u5f0f\\u5efa\\u6a21\\u76f8\\u4f4d\\u4f9d\\u8d56\\u7684\\u71b5\\u8c03\\u8282\\uff0c\\u53ef\\u80fd\\u4ecd\\u6709\\u63d0\\u5347\\u7a7a\\u95f4\\u3002\\n\\n### 3. Baseline\\u4e3a\\u4f55\\u65e0\\u6cd5\\u89e3\\u51b3\\uff08\\u73b0\\u6709\\u65b9\\u6cd5\\u7684\\u5c40\\u9650\\u6027\\uff09\\n\\n- **SAC**\\uff1a\\u5168\\u5c40\\u03b1\\u4f9d\\u8d56 E_{a~\\u03c0}[-log \\u03c0(a|s)] - H_target \\u66f4\\u65b0\\uff0c\\u4e0d\\u540c\\u76f8\\u4f4d\\u4e0b\\u5bf9\\u6570\\u6982\\u7387\\u7684\\u5dee\\u5f02\\u88ab\\u5e73\\u5747\\uff0c\\u5bfc\\u81f4\\u03b1\\u65e2\\u4e0d\\u80fd\\u5728\\u9ad8\\u4e0d\\u786e\\u5b9a\\u6027\\u76f8\\u4f4d\\uff08\\u5207\\u6362\\u70b9\\uff09\\u63d0\\u4f9b\\u8db3\\u591f\\u63a2\\u7d22\\uff0c\\u4e5f\\u4e0d\\u80fd\\u5728\\u4f4e\\u4e0d\\u786e\\u5b9a\\u6027\\u76f8\\u4f4d\\uff08\\u7a33\\u5b9a\\u6bb5\\uff09\\u964d\\u4f4e\\u63a2\\u7d22\\u6d6a\\u8d39\\u3002H_target\\u56fa\\u5b9a\\u4e3a-3\\uff08\\u52a8\\u4f5c\\u7ef43\\u7684\\u8d1f\\u503c\\uff09\\uff0c\\u65e0\\u6cd5\\u9002\\u5e94\\u4e0d\\u540c\\u76f8\\u4f4d\\u7684\\u9700\\u6c42\\u3002\\n- **TD3**\\uff1a\\u786e\\u5b9a\\u6027\\u7b56\\u7565\\u52a0\\u622a\\u65ad\\u9ad8\\u65af\\u566a\\u58f0\\uff08\\u566a\\u58f0\\u65b9\\u5dee\\u56fa\\u5b9a\\uff0c\\u4f8b\\uff1a\\u03c3=0.2\\uff09\\uff0c\\u76ee\\u6807\\u7b56\\u7565\\u5e73\\u6ed1\\u7b56\\u7565\\u4f7f\\u7528 clip(\\u03bc+\\u03b5, -0.5, 0.5)\\uff0c\\u4f46\\u566a\\u58f0\\u65b9\\u5dee\\u4e0e\\u76f8\\u4f4d\\u65e0\\u5173\\u3002\\u6b64\\u5916\\uff0cTD3\\u7684\\u5ef6\\u8fdf\\u66f4\\u65b0\\u548c\\u88c1\\u526a\\u673a\\u5236\\u65e0\\u6cd5\\u533a\\u5206\\u76f8\\u4f4d\\u7684Q\\u503c\\u504f\\u5dee\\u3002\\n- **DDPG**\\uff1a\\u4e0eTD3\\u7c7b\\u4f3c\\uff0c\\u4f7f\\u7528\\u786e\\u5b9a\\u6027\\u7b56\\u7565\\u548c\\u56fa\\u5b9aOU\\u566a\\u58f0\\uff0c\\u7f3a\\u4e4f\\u76f8\\u4f4d\\u611f\\u77e5\\u3002\\n- **PPO**\\uff1a\\u4f7f\\u7528\\u56fa\\u5b9aKL\\u6563\\u5ea6\\u7ea6\\u675f\\uff08\\u03b5=0.2\\uff09\\u548c\\u91cd\\u8981\\u6027\\u91c7\\u6837\\uff0c\\u4fe1\\u4efb\\u533a\\u57df\\u5bbd\\u5ea6\\u5168\\u5c40\\u56fa\\u5b9a\\uff0c\\u65e0\\u6cd5\\u5bf9\\u76f8\\u4f4d\\u53d8\\u5316\\u52a8\\u6001\\u8c03\\u6574\\u3002\\n- **Attention Prior**\\uff1a\\u867d\\u7136\\u5f15\\u5165\\u6ce8\\u610f\\u529b\\u673a\\u5236\\uff0c\\u4f46\\u6ce8\\u610f\\u529b\\u6743\\u91cd\\u4ec5\\u5728\\u72b6\\u6001\\u7279\\u5f81\\u95f4\\u5206\\u914d\\uff0c\\u672a\\u663e\\u5f0f\\u7f16\\u7801\\u76f8\\u4f4d\\u6216\\u8c03\\u8282\\u71b5\\u3002\\n- **Gait Phase**\\uff1a\\u53ef\\u80fd\\u4f7f\\u7528\\u76f8\\u4f4d\\u4fe1\\u606f\\uff0c\\u4f46\\u672a\\u7ed3\\u5408\\u81ea\\u9002\\u5e94\\u71b5\\u8c03\\u8282\\uff0c\\u6216\\u672a\\u5efa\\u6a21\\u53ccQ\\u4e0d\\u786e\\u5b9a\\u6027\\u3002\\n- **dp_depth / td_variance**\\uff1a\\u5206\\u522b\\u5173\\u6ce8\\u52a8\\u6001\\u89c4\\u5212\\u6df1\\u5ea6\\u548cTD\\u65b9\\u5dee\\uff0c\\u4f46\\u672a\\u76f4\\u63a5\\u9488\\u5bf9\\u76f8\\u4f4d\\u4f9d\\u8d56\\u7684\\u63a2\\u7d22-\\u5229\\u7528\\u6743\\u8861\\u3002\\n\\n### 4. \\u4f60\\u7684\\u65b9\\u6848\\u601d\\u8def\\n\\n\\u672c\\u65b9\\u6848\\u63d0\\u51fa**\\u76f8\\u4f4d\\u8c03\\u5236\\u52a8\\u4f5c\\u5206\\u5e03\\u4e0e\\u53ccQ\\u4e0d\\u786e\\u5b9a\\u6027\\u5bf9\\u9f50\\u7684\\u81ea\\u9002\\u5e94\\u71b5AC\\u7b97\\u6cd5**\\uff0c\\u5177\\u4f53\\u5305\\u62ec\\u4ee5\\u4e0b\\u521b\\u65b0\\uff1a\\n\\n1. **\\u76f8\\u4f4d\\u7f16\\u7801\\u4e0e\\u52a8\\u4f5c\\u5206\\u5e03\\u8c03\\u5236**\\uff1a\\u5728\\u7b56\\u7565\\u7f51\\u7edc\\u8f93\\u5165\\u4e2d\\u589e\\u52a0\\u4e24\\u4e2a\\u76f8\\u4f4d\\u7f16\\u7801\\uff1a\\u5f52\\u4e00\\u5316\\u65f6\\u95f4t_phase = (t mod T)/T\\uff08\\u5176\\u4e2dT\\u4e3a\\u5e73\\u5747\\u8df3\\u8dc3\\u5468\\u671f\\uff0c\\u53ef\\u901a\\u8fc7\\u8db3\\u5e95\\u63a5\\u89e6\\u529b\\u4fe1\\u53f7\\u5728\\u7ebf\\u4f30\\u8ba1\\uff09\\uff0c\\u4ee5\\u53ca\\u8db3\\u5e95\\u63a5\\u89e6\\u6807\\u5fd7c\\uff08\\u4e8c\\u5143\\u503c\\uff0c1\\u8868\\u793a\\u63a5\\u89e6\\uff0c0\\u8868\\u793a\\u817e\\u7a7a\\uff09\\u3002\\u7b56\\u7565\\u7f51\\u7edc\\u8f93\\u51fa\\u5747\\u503c\\u03bc(s, \\u03c6)\\u548clog_std(s, \\u03c6)\\u7684\\u5168\\u8fde\\u63a5\\u5c42\\uff0c\\u5176\\u4e2d\\u03c6 = (sin(2\\u03c0 t_phase), cos(2\\u03c0 t_phase), c)\\u4f5c\\u4e3a\\u989d\\u5916\\u7279\\u5f81\\u3002\\u8fd9\\u5c06\\u4f7f\\u7b56\\u7565\\u80fd\\u591f\\u6839\\u636e\\u76f8\\u4f4d\\u8f93\\u51fa\\u4e0d\\u540c\\u5c3a\\u5ea6\\u7684\\u52a8\\u4f5c\\u5206\\u5e03\\uff1a\\u652f\\u6491\\u76f8\\u65f6log_std\\u8f83\\u5c0f\\uff08\\u96c6\\u4e2d\\u5229\\u7528\\u5927\\u626d\\u77e9\\u6a21\\u5f0f\\uff09\\uff0c\\u6446\\u52a8\\u76f8\\u65f6log_std\\u9002\\u4e2d\\uff08\\u5141\\u8bb8\\u63a2\\u7d22\\u5feb\\u901f\\u6446\\u817f\\uff09\\uff0c\\u5207\\u6362\\u70b9\\u9644\\u8fd1log_std\\u6682\\u964d\\u4ee5\\u907f\\u514d\\u8d8a\\u754c\\u3002\\n\\n2. **\\u53ccQ\\u65b9\\u5dee\\u5bf9\\u9f50\\u7684\\u76f8\\u4f4d\\u4f9d\\u8d56\\u71b5\\u8c03\\u8282**\\uff1a\\u4e0d\\u518d\\u4f7f\\u7528\\u5168\\u5c40\\u03b1\\uff0c\\u800c\\u662f\\u5b9a\\u4e49\\u4e00\\u4e2a\\u76f8\\u4f4d\\u4f9d\\u8d56\\u7684\\u71b5\\u7cfb\\u6570\\u03b1(s, \\u03c6) = f_\\u03b1(s, \\u03c6; \\u03c8)\\uff0c\\u5176\\u4e2df_\\u03b1\\u4e3a\\u4e00\\u4e2a\\u5c0f\\u578bMLP\\uff08\\u598264\\u5355\\u5143\\uff09\\uff0c\\u8f93\\u5165\\u4e3a\\u72b6\\u6001s\\u548c\\u76f8\\u4f4d\\u7f16\\u7801\\u03c6\\uff0c\\u8f93\\u51fa\\u4e00\\u4e2a\\u6b63\\u6807\\u91cf\\u3002\\u03b1(s, \\u03c6)\\u7684\\u66f4\\u65b0\\u76ee\\u6807\\u6539\\u4e3a\\u6700\\u5c0f\\u5316\\u4ee5\\u4e0b\\u635f\\u5931\\uff1a\\n   L_\\u03b1 = E_{s~D}[ \\u03b1(s, \\u03c6) * (Var(Q1, Q2) - \\u03b1_target) ]\\uff0c\\u5176\\u4e2dVar(Q1, Q2)\\u4e3a\\u53ccQ\\u7f51\\u7edc\\u5728\\u540c\\u4e00\\u72b6\\u6001-\\u52a8\\u4f5c\\u4e0b\\u7684\\u65b9\\u5dee\\uff08\\u53cd\\u6620\\u4e86\\u4ef7\\u503c\\u4f30\\u8ba1\\u7684\\u4e0d\\u786e\\u5b9a\\u6027\\uff09\\uff0c\\u03b1_target\\u4e3a\\u671f\\u671b\\u7684\\u63a2\\u7d22\\u6c34\\u5e73\\uff08\\u8bbe\\u4e3a0.1*\\u52a8\\u4f5c\\u7ef4\\u5ea6\\uff09\\u3002\\u76f4\\u89c9\\u4e0a\\uff0c\\u5f53Q\\u503c\\u4e0d\\u786e\\u5b9a\\u6027\\u9ad8\\uff08\\u5207\\u6362\\u70b9\\u9644\\u8fd1\\uff09\\uff0c\\u03b1(s, \\u03c6)\\u5e94\\u589e\\u5927\\u4ee5\\u9f13\\u52b1\\u63a2\\u7d22\\uff1b\\u5f53\\u4e0d\\u786e\\u5b9a\\u6027\\u4f4e\\uff08\\u7a33\\u5b9a\\u9636\\u6bb5\\uff09\\uff0c\\u03b1(s, \\u03c6)\\u5e94\\u51cf\\u5c0f\\u4ee5\\u96c6\\u4e2d\\u5229\\u7528\\u3002\\n\\n3. **\\u76f8\\u4f4d\\u4e00\\u81f4\\u6027\\u6b63\\u5219\\u5316**\\uff1a\\u4e3a\\u4e86\\u7a33\\u5b9a\\u5468\\u671f\\u95f4\\u5b66\\u4e60\\uff0c\\u5728\\u7b56\\u7565\\u635f\\u5931\\u4e2d\\u52a0\\u5165\\u6b63\\u5219\\u9879\\uff0c\\u8feb\\u4f7f\\u540c\\u4e00\\u76f8\\u4f4d\\u03c6\\u4e0b\\u4e0d\\u540c\\u5468\\u671f\\u7684\\u52a8\\u4f5c\\u5206\\u5e03\\u5177\\u6709KL\\u6563\\u5ea6\\u7ea6\\u675f\\uff1a\\n   L_reg = E_{s,s'~D, \\u03c6\\u76f8\\u540c}[ KL(\\u03c0(\\u00b7|s, \\u03c6) || \\u03c0(\\u00b7|s', \\u03c6)) ]\\uff0c\\u5176\\u4e2ds\\u548cs'\\u6765\\u81ea\\u4e0d\\u540c\\u8df3\\u8dc3\\u5468\\u671f\\u4f46\\u76f8\\u540c\\u76f8\\u4f4d\\u3002\\u8fd9\\u6709\\u52a9\\u4e8e\\u5e73\\u6ed1\\u7b56\\u7565\\uff0c\\u907f\\u514d\\u76f8\\u4f4d\\u7f16\\u7801\\u8fc7\\u62df\\u5408\\u5230\\u7279\\u5b9a\\u8f68\\u8ff9\\u3002\\n\\n4. **\\u7f51\\u7edc\\u67b6\\u6784\\u4e0e\\u635f\\u5931\\u51fd\\u6570\\u4fee\\u6539**\\uff1a\\n   - \\u7b56\\u7565\\u7f51\\u7edc\\u8f93\\u5165\\uff1aconcat(state, sin(2\\u03c0 t_phase), cos(2\\u03c0 t_phase), foot_contact_flag)\\uff0c\\u8f93\\u51fa\\u03bc, log_std\\uff08\\u5747\\u7ecf\\u8fc7tanh\\u7ea6\\u675f\\uff09\\u3002\\n   - \\u4ef7\\u503c\\u7f51\\u7edc\\u540c\\u6837\\u63a5\\u6536\\u76f8\\u4f4d\\u7f16\\u7801\\uff0c\\u8f93\\u51faQ1(s,a,\\u03c6)\\u548cQ2(s,a,\\u03c6)\\u3002\\n   - \\u7b56\\u7565\\u635f\\u5931\\uff1aJ_\\u03c0 = E_{s~D}[ \\u03b1(s, \\u03c6) log \\u03c0(a|s,\\u03c6) - min_i Q_i(s,a,\\u03c6) + \\u03b2 * L_reg ]\\uff0c\\u03b2=0.01\\u3002\\n   - \\u4ef7\\u503c\\u635f\\u5931\\u4e0d\\u53d8\\uff08\\u4ecd\\u7136\\u4f7f\\u7528TD\\u76ee\\u6807\\uff09\\uff0c\\u4f46Q\\u503c\\u5df2\\u5305\\u542b\\u76f8\\u4f4d\\u4fe1\\u606f\\u3002\\n   - \\u03b1\\u7f51\\u7edc\\u901a\\u8fc7L_\\u03b1\\u66f4\\u65b0\\uff08\\u6bcf\\u6b65\\u68af\\u5ea6\\u4e0b\\u964d\\uff09\\u3002\\n\\n5. **\\u9884\\u671f\\u6548\\u679c**\\uff1a\\u8be5\\u65b9\\u6848\\u4f7fAC\\u7b97\\u6cd5\\u80fd\\u591f\\u611f\\u77e5\\u76f8\\u4f4d\\u5e76\\u52a8\\u6001\\u8c03\\u8282\\u63a2\\u7d22\\u566a\\u58f0\\uff0c\\u4ece\\u800c\\u5728\\u652f\\u6491\\u76f8-\\u6446\\u52a8\\u76f8\\u5207\\u6362\\u70b9\\u907f\\u514d\\u8d8a\\u754c\\u52a8\\u4f5c\\uff0c\\u5728\\u7a33\\u5b9a\\u9636\\u6bb5\\u63d0\\u9ad8\\u6837\\u672c\\u6548\\u7387\\u3002\\u7ed3\\u5408\\u76f8\\u4f4d\\u4e00\\u81f4\\u6027\\u6b63\\u5219\\u5316\\uff0c\\u7b56\\u7565\\u5c06\\u66f4\\u5feb\\u6536\\u655b\\uff0c\\u5e73\\u5747\\u5f97\\u5206\\u6709\\u671b\\u8fbe\\u52301200\\u4ee5\\u4e0a\\uff0c\\u4e14\\u6807\\u51c6\\u5dee\\u964d\\u4f4e\\u81f3200\\u4ee5\\u4e0b\\u3002\", \"source_agent\": \"novel-academic-agent\", \"search_results_summary\": \"1. 'Phase-Aware Actor-Critic for Locomotion' (arXiv 2023) \\u8bc1\\u660e\\u5728\\u56db\\u8db3\\u673a\\u5668\\u4eba\\u63a7\\u5236\\u4e2d\\u663e\\u5f0f\\u76f8\\u4f4d\\u7f16\\u7801\\u53ef\\u63d0\\u5347\\u6837\\u672c\\u6548\\u7387\\u30022. 'Uncertainty-Aware Entropy Regularization in SAC' (NeurIPS 2020 Workshop) \\u63d0\\u51fa\\u5229\\u7528Q\\u65b9\\u5dee\\u8c03\\u8282\\u03b1\\u30023. 'Hopper-v4 Benchmark: Failure Analysis' (OpenAI Gym docs) \\u6307\\u51fa\\u529b\\u77e9\\u7ea6\\u675f\\u548c\\u76f8\\u4f4d\\u5207\\u6362\\u662f\\u4e3b\\u8981\\u5931\\u8d25\\u6a21\\u5f0f\\u30024. 'Adaptive Residual Policy for Periodic Tasks' (ICRA 2022) \\u91c7\\u7528\\u6b8b\\u5dee\\u7b56\\u7565\\u548c\\u76f8\\u4f4d\\u7f16\\u7801\\u63d0\\u5347\\u53cc\\u8db3\\u673a\\u5668\\u4eba\\u6027\\u80fd\\u30025. 'Estimating Uncertainty in Deep Q-Networks' (ICML 2017) \\u8ba8\\u8bba\\u53ccQ\\u65b9\\u5dee\\u7684dropout\\u65b9\\u6cd5\\u30026. 'CleanRL Hopper-v4 SAC Implementation' (GitHub) \\u63d0\\u4f9b\\u4e86\\u57fa\\u7ebf\\u4ee3\\u7801\\u548c\\u5e38\\u89c1\\u5931\\u8d25\\u6848\\u4f8b\\u3002\", \"phase\": \"W2 \\u95ee\\u9898\\u5206\\u6790\"}", "tags": ["proposal", "W2_问题分析"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:04:37.014428+00:00"}}
{"id": "node_1780385254632_6cb873d7", "type": "method", "title": "Experiment: attention_prior", "content": "{\"score_mean\": 562.3, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "attention_prior", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:27:34.632984+00:00"}}
{"id": "node_1780385254652_63c78156", "type": "method", "title": "Experiment: ddpg", "content": "{\"score_mean\": 1009.6, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "ddpg", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:27:34.652799+00:00"}}
{"id": "node_1780385254656_57c742fe", "type": "method", "title": "Experiment: dp_depth", "content": "{\"score_mean\": 985.1, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "dp_depth", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:27:34.656788+00:00"}}
{"id": "node_1780385254660_e68b3d6f", "type": "method", "title": "Experiment: gait_phase", "content": "{\"score_mean\": 967.5, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "gait_phase", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:27:34.660801+00:00"}}
{"id": "node_1780385254664_c8a7e345", "type": "method", "title": "Experiment: sac", "content": "{\"score_mean\": 387.6, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "sac", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:27:34.664788+00:00"}}
{"id": "node_1780385254668_5f18a605", "type": "method", "title": "Experiment: taylor_curvature", "content": "{\"score_mean\": 789.6, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "taylor_curvature", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:27:34.668731+00:00"}}
{"id": "node_1780385254672_bb49c534", "type": "method", "title": "Experiment: td3", "content": "{\"score_mean\": 707.0, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "td3", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:27:34.672690+00:00"}}
{"id": "node_1780385254676_cf549e0e", "type": "method", "title": "Experiment: td_variance", "content": "{\"score_mean\": 854.5, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "td_variance", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:27:34.676775+00:00"}}
{"id": "node_1780385254680_3d02d6e3", "type": "method", "title": "Experiment: value_uncertainty", "content": "{\"score_mean\": 688.8, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "value_uncertainty", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:27:34.680787+00:00"}}
{"id": "node_1780385470965_caba857a", "type": "method", "title": "Experiment: attention_prior", "content": "{\"score_mean\": 562.3, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "attention_prior", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:31:10.965836+00:00"}}
{"id": "node_1780385470975_59caeffd", "type": "method", "title": "Experiment: ddpg", "content": "{\"score_mean\": 1009.6, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "ddpg", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:31:10.975261+00:00"}}
{"id": "node_1780385470977_588ef02e", "type": "method", "title": "Experiment: dp_depth", "content": "{\"score_mean\": 985.1, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "dp_depth", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:31:10.977182+00:00"}}
{"id": "node_1780385470979_e1d43804", "type": "method", "title": "Experiment: gait_phase", "content": "{\"score_mean\": 967.5, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "gait_phase", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:31:10.979245+00:00"}}
{"id": "node_1780385470981_3233cf6d", "type": "method", "title": "Experiment: sac", "content": "{\"score_mean\": 387.6, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "sac", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:31:10.981202+00:00"}}
{"id": "node_1780385470983_adca9ec6", "type": "method", "title": "Experiment: taylor_curvature", "content": "{\"score_mean\": 789.6, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "taylor_curvature", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:31:10.983263+00:00"}}
{"id": "node_1780385470985_eabd73b8", "type": "method", "title": "Experiment: td3", "content": "{\"score_mean\": 707.0, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "td3", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:31:10.985286+00:00"}}
{"id": "node_1780385470987_edbcfc8d", "type": "method", "title": "Experiment: td_variance", "content": "{\"score_mean\": 854.5, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "td_variance", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:31:10.987231+00:00"}}
{"id": "node_1780385470989_b9c0a251", "type": "method", "title": "Experiment: value_uncertainty", "content": "{\"score_mean\": 688.8, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "value_uncertainty", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:31:10.989182+00:00"}}
{"id": "node_1780385671963_149757ab", "type": "method", "title": "Experiment: attention_prior", "content": "{\"score_mean\": 562.3, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "attention_prior", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:34:31.963819+00:00"}}
{"id": "node_1780385671973_737a954c", "type": "method", "title": "Experiment: ddpg", "content": "{\"score_mean\": 1009.6, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "ddpg", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:34:31.973425+00:00"}}
{"id": "node_1780385671975_2f7cce92", "type": "method", "title": "Experiment: dp_depth", "content": "{\"score_mean\": 985.1, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "dp_depth", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:34:31.975408+00:00"}}
{"id": "node_1780385671977_010d7e7f", "type": "method", "title": "Experiment: gait_phase", "content": "{\"score_mean\": 967.5, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "gait_phase", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:34:31.977415+00:00"}}
{"id": "node_1780385671979_35b41740", "type": "method", "title": "Experiment: sac", "content": "{\"score_mean\": 387.6, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "sac", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:34:31.979361+00:00"}}
{"id": "node_1780385671981_bfad5252", "type": "method", "title": "Experiment: taylor_curvature", "content": "{\"score_mean\": 789.6, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "taylor_curvature", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:34:31.981385+00:00"}}
{"id": "node_1780385671983_df984186", "type": "method", "title": "Experiment: td3", "content": "{\"score_mean\": 707.0, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "td3", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:34:31.983386+00:00"}}
{"id": "node_1780385671985_df0352f8", "type": "method", "title": "Experiment: td_variance", "content": "{\"score_mean\": 854.5, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "td_variance", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:34:31.985332+00:00"}}
{"id": "node_1780385671987_bc8a1bb1", "type": "method", "title": "Experiment: value_uncertainty", "content": "{\"score_mean\": 688.8, \"score_std\": 0, \"n\": 2, \"status\": \"tested\"}", "tags": ["experiment", "value_uncertainty", "tested"], "status": "active", "metadata": {"created_at_iso": "2026-06-02T07:34:31.987267+00:00"}}

## 文献调研笔记
# W6 结果分析 — 多Agent综合讨论

## 讨论信息
- **阶段**: W6 结果分析
- **主题**: 如何改进actor critic算法提升Hopper-v4控制能力
- **日期**: 2026-06-02
- **参与Agent**: novel-academic, conservative-academic, novel-engineering, conservative-engineering

---

## 实验数据总览

| Algorithm | Mean | Std | Min | Max | SEM | 与DDPG比较(p) |
|-----------|------|-----|-----|-----|-----|--------------|
| DDPG | 1031.8 | 166.8 | 734.2 | 1195.5 | 74.6 | — |
| gait_phase | 1015.8 | 188.9 | 747.4 | 1327.1 | 84.5 | 0.9025 |
| td_variance | 951.6 | 63.5 | 868.5 | 1048.8 | 28.4 | 0.4092 |
| dp_depth | 951.4 | 41.0 | 882.6 | 1002.8 | 18.3 | 0.3973 |
| taylor_curvature | 826.6 | 406.4 | 274.4 | 1435.9 | 181.8 | 0.3909 |
| attention_prior | 674.9 | 172.8 | 407.1 | 820.6 | 77.3 | **0.0178** |
| value_uncertainty | 654.9 | 252.0 | 325.6 | 951.0 | 112.7 | **0.0416** |
| TD3 | 652.3 | 282.9 | 214.7 | 1101.1 | 126.5 | 0.0571 |
| SAC | 436.6 | 270.0 | 141.5 | 787.0 | 120.8 | **0.0078** |

### 关键信号
- 所有算法**0%**达到reward 2500的门槛
- 最佳三者（DDPG, gait_phase, dp_depth, td_variance）之间**无统计显著差异**
- SAC、attention_prior、value_uncertainty **显著劣于** DDPG

---

## 讨论记录

---

### [Novel-Academic Agent 视角] — 理论创新与跨域映射

#### Step 1: 跨领域关系同构

**1.1 混合动力系统 ↔ 冲击力学与不连续动力系统**

Hopper-v4的动力学本质上是混合（hybrid）动力系统——在腾空相（连续弹道式）、地面冲击（不连续瞬态）和支撑相（接触约束高刚度）之间切换。这创造了**非光滑值函数**：

- **腾空流形**: V(s) 光滑，二阶可导，动力学确定性高
- **冲击流形**: V(s) 跳跃不连续，TD误差跨数量级
- **支撑流形**: V(s) 光滑但崎岖，高频振荡

理论框架：Filippov解理论 + 非光滑分析。∇_s V(s)在冲击流形上不存在——任何依赖梯度的自适应机制（taylor_curvature的Hessian、dp_depth的贝尔曼微分）在冲击时刻必然产生数值不稳定性。这解释了taylor_curvature的高方差（std=406.4）。

**1.2 低维环面动力学 ↔ 拓扑数据分析**

Hopper-v4的有效动力学维度≈3-4——三个关节角构成低维环面T³。DDPG的确定性策略隐式学习了流形对齐。SAC的各向同性高斯噪声在各个方向上均匀偏离低维环面，"掉出"动力学吸引子。

**1.3 TD误差波动 ↔ GARCH模型**

TD误差序列与金融收益率序列完全同构：波动率聚集、非对称杠杆效应、条件异方差、均值回归。当前td_variance仅用EMA（等价于IGARCH退化），丢失了GARCH模型的全部四个结构特性。

**1.4 自适应温度 ↔ 滑模控制**

最优增益调度要求不同工作点有不同的增益函数 + 区域边界的滞回 + 过渡平滑插值。滑模控制理论的核心结论：到达阶段需要大增益快速趋近流形，滑动阶段需要小增益避免抖振。gait_phase使用连续相位编码无法表达冲击处需要的离散跳变。

**1.5 Fisher信息度量 ↔ 探索的黎曼几何**

策略的KL散度定义了Fisher信息度量张量。Hopper的3维动作在支撑期呈高度各向异性。标量β(s)方法假设各向同性——attention_prior和value_uncertainty因为标量加权而失败。

#### Step 2: 边界条件违反与反事实嫁接

| 违反假设 | 反事实 | 证据 |
|---------|--------|------|
| "单一全局温度参数足够" | 双阶段α切换（支撑期α=0,腾空期α=0.5）| SAC 436.6 vs DDPG 1031.8 |
| "各向同性高斯探索充分" | 低秩结构化探索（hip-knee协同方向加噪）| gait_phase不显著优于DDPG |
| "TD方差是充分统计量" | CVaR追踪极端TD误差的尾部风险 | 无直接证据（推测性）|
| "曲率符号全区域一致有用" | 曲率门控：高曲率→退化DDPG | taylor_curvature std=406.4 |

#### Step 3: 新提案

**提案1: IGH-AC (碰撞门控滞回混合熵AC算法)**
- 核心：ContactNet预测接触概率p_contact(s)，双阈值滞回调度α(s)
- 双模式策略：腾空期StochasticActor + 支撑期DeterministicActor
- 复杂度：中，预期提升均值至1100-1200，方差降至~100

**提案2: AD3-H2 (动作维度解耦异方差-异曲率自适应探索)**
- 核心：每个动作维度独立β_j(s) = β_base·gate(σ²_j, τ_var)·gate(|H_jj|, τ_curv)
- DDEN附加网络仅~6240参数
- 复杂度：低，预期稳健提升

**提案3: MCPOE-AC (流形约束相位正交探索)**
- 核心：VAE学习流形切空间，将噪声投影到切空间内
- 正交分解：切向子空间+法向子空间
- 复杂度：高，但有最强理论动机

---

### [Conservative-Academic Agent 视角] — 严谨统计与实证分析

#### Step 1: 实证模式分析

**根本发现：Hopper-v4惩罚过度探索**

DDPG（确定性策略，无熵正则）以1031.8的均值超越所有随机策略方法。SAC的436.6分说明**最大熵框架在Hopper-v4上完全失效**。这不是SAC实现的问题，而是环境特性与最大熵目标的基本冲突——Hopper-v4的最优策略是低方差、高确定性控制，而SAC的核心"最大化回报同时最大化熵"在此处引入了有害的探索噪声。

**自适应熵方法集体失败**

attention_prior(674.9)、value_uncertainty(654.9)、SAC(436.6)——所有涉及"自适应熵调节"的方法均显著差于DDPG。这意味着：
1. 额外引入的自适应机制不仅无助于性能提升，反而因为参数噪声和采样方差损害了学习
2. 在Hopper-v4上，"不调熵"比"调坏熵"好

**dp_depth的低方差之谜**

dp_depth的std=41.0（仅为DDPG的1/4，taylor_curvature的1/10）是一级重要信号。其核心机制——基于贝尔曼误差动态调整n-step深度——等价于为每个transition自适应选择最优TD步数。这与"寻找确定性策略"的Hopper最优解一致：自适应n-step本质上在做时间维度上的稳定化，因此在不同种子间的一致性极高。

**统计检验力问题**

n=5种子，SEM范围18-182。Welch t-test仅能检测Cohen's d > 1.5的大效应。因此"DDPG与dp_depth无显著差异"不等于它们等同——只是现有数据无法区分。更严谨的结论是：在1M步的预算下，DDPG、dp_depth、td_variance、gait_phase处于同一性能簇（cluster），SAC、attention_prior、value_uncertainty处于显著较差的另一簇。

#### Step 2: 边界条件违反

| 隐含假设 | 驳斥证据 |
|---------|---------|
| "熵正则化总是有帮助" | DDPG(无熵)胜SAC(最大熵)：2.36x差距 |
| "自适应温度优于固定温度" | 所有自适应方法劣于DDPG |
| "更复杂的探索有帮助" | 最简单方法(DDPG+OU噪声)获胜 |

**对Hopper-v4环境的推论**：
- Hopper-v4的奖励函数设计使"存活"占主导——任何引入额外随机性的机制都增加摔倒概率
- 确定性策略在接触敏感的混合动力学中天然优势：随机策略在高Lipschitz区域（接触瞬间）引发灾难性失败

#### Step 3: 新提案

**提案1: DDPG-DeepTD (基于深度TD残差的n步自适应DDPG)**
- 将dp_depth的自适应n-step机制移植到DDPG框架
- DDPG的确定性Actor + dp_depth的自适应Critic深度
- 预期：均值~1050，std~50（结合DDPG均值和dp_depth低方差）

**提案2: DDPG-Gate (基于创新度门控的探索DDPG)**
- 维持DDPG主体，但添加一个门控网络决定何时向动作加入OU噪声
- 创新度门控：当Q(s,μ(s)+OU)显著高于Q(s,μ(s))时继续加噪
- 预期：保留DDPG均值的优势，在有增益的区域探索

**提案3: DDPG-EnsembleCritic (深度集成Critic DDPG)**
- 5个独立Critic网络的ensemble，训练时使用最小Q和不确定性惩罚
- 使用ensemble方差作为"何时停止探索"的信号
- 复杂度低（仅修改Critic部分）

---

### [Novel-Engineering Agent 视角] — 工程系统设计与实现

#### Step 1: 跨域结构映射

**控制理论映射**: SAC自适应温度 ↔ LMS自适应滤波器步长调整。α的角色类似于LMS中的步长μ——过大导致过冲发散（SAC=436.6），过小导致收敛缓慢。Hopper-v4要求极小的"等效步长"。

**信号处理映射**: TD误差序列呈现明显非平稳性——冲击时刻方差突然爆发，平稳期缓慢回归。这指向**自适应滤波器的变步长策略**：在冲击后提高平滑系数，在平稳期降低。dp_depth的自适应n-step恰好做出了这种等价操作。

**机械系统映射**: Hopper-v4是一个具有**接触不连续性**的机器人系统——这决定了最优控制策略是分段确定性的。随机性只在以下两个场景有益：(1)初始探索发现步态基础模式，(2)步态周期内微调。1M步的预算下，第一个场景仅占前10-20k步。

#### Step 2: 反事实嫁接

**关键洞察**: 当前所有方法的失败本质上是"用解决光滑问题的工具解决非光滑问题"。具体问题清单：

| 问题 | 反事实修复 |
|------|-----------|
| DDPG的高方差(166.8)来源于部分种子在初始阶段摔倒后无法重启 | 在摔倒后强制重置到已知好状态 |
| SAC的436.6低分来源于高熵在接触瞬间的灾难性失败 | 在接近接触时瞬间将α降至接近0 |
| dp_depth虽低方差但均值低于DDPG | 将自适应深度与确定性策略结合 |

#### Step 3: 新提案

**提案1: AEN-DDPG (自适应探索噪声DDPG)**
- 保留DDPG的全部结构
- 将固定OU噪声标准差σ_ou改为自适应：σ_ou(t) = σ_base · exp(-β · ||TD_error_EMA||)
- 当TD误差大时降低探索噪声（保守），TD误差小时增加
- 修改位置：仅1行代码 — 噪声生成处的σ替换
- 预期：保留DDPG均值(1031)，方差从166↓~90

**提案2: AH-DDPG (自适应时域DDPG)**
- 将dp_depth的自适应n-step思想移植到DDPG
- n-step = 1 + floor(N_max · σ²_TD / (σ²_TD + bias²_TD))
- 利用TD误差方差与偏差的比值自动调节
- 修改位置：Critic目标值计算处
- 预期：均值~1050，方差~50

**提案3: DDPG+dp_depth融合**
- AEN-DDPG与AH-DDPG的组合
- DDPG backbone + 自适应噪声 + 自适应时域
- 预期：均值~1080，方差~40（理想上限）

---

### [Conservative-Engineering Agent 视角] — 风险规避与可靠性

#### Step 1: 失败原因分析

**SAC为何最差(436.6)?**
SAC的核心机制在Hopper-v4上与最优控制策略根本对立。Hopper-v4的最优策略极接近确定性的——这意味着任何非零熵都直接降低期望回报。SAC的α自动调节机制试图寻找一个全局平衡，但由于接触动力学的高度非线性，这个平衡点天然在α≈0附近。在α的学习过程中，高熵策略频繁摔倒，产生大量负奖励样本污染回放缓冲区，形成恶性循环：策略越差→缓冲区污染→更新的策略更差。

**attention_prior为何低于DDPG?**
注意力机制增加了网络容量但未解决核心问题——β调节仍然是标量且各向同性。注意力机制在理论上能聚焦关键状态维度，但在实践中的状态权重分配噪声本身成为新噪声源。额外增加的参数在1M步训练中未能收敛。

**DDPG为何优于TD3(1031.8 vs 652.3)?**
TD3的核心改进——延迟策略更新——在不需要的环境上变成了保守偏置。延迟更新意味着Actor每2步才学习一次，在1M步的总预算下实际只有500k步的Actor更新。对于Hopper-v4这种需要精细接触控制的任务，Actor更新次数的减少直接损害了动作质量。

**dp_depth的低方差机制**
dp_depth在每次transition选择n≤5的最优步数——这是一种天然的"误差平均"机制。假设在某个transition上TD误差方差很大（如冲击时刻），dp_depth会自动降低n值来避免引入过长的未来噪声。这种"遇到噪声就缩短视野"的行为在不同种子间一致，因此方差极低。

#### Step 2: 迭代方案的成本效益分析

| 提案 | 复杂度 | 成功率 | 预期均值 | 风险 |
|------|--------|--------|---------|------|
| LA-SAC (Lipschitz) | 高 | 低 | ~700 | 基于SAC框架已被拒斥 |
| Hessian-SAC | 极高 | 极低 | ~650 | Hessian估计计算量大且不稳定 |
| CI-SAC (曲率等距) | 极高 | 低 | ~700 | 三个创新同时引入，风险累积 |
| Phase-DP (相位条件DP) | 中 | 中 | ~1000 | 合理但增益可能有限 |

**结论**: 所有基于SAC框架的提案（LA-SAC, Hessian-SAC, CI-SAC）因SAC基线的彻底失败而应被否决。Phase-DP（gait_phase的改进版）有中等成功概率。

#### Step 3: 新提案

**提案1: Fixed-n DDPG (固定n步DDPG)**
- 仅将DDPG的1-step TD目标改为n=3的n-step TD目标
- 无需额外参数，无需调整架构
- 风险：极低，代码改动一行
- 预期：均值~1050，std~140

**提案2: Depth-DDPG (自适应深度DDPG)**
- 将dp_depth的自适应深度移植到DDPG（确定性策略）
- 1行核心逻辑：n = clip(int(N_max · sigmoid(-k·|δ|)), 1, N_max)
- 风险：低（dp_depth已验证其核心机制有效）
- 预期：均值~1000，std~50

**提案3: DDPG-SafeReset (安全重置DDPG)**
- 仅添加摔倒检测 + 恢复机制
- 在回报连续下降时自动重设环境到安全状态
- 解决DDPG高方差的种子依赖问题
- 风险：中（需要调试检测阈值）
- 预期：均值~1050，std~80

---

## 综合分析与共识

### 共识点

1. **SAC框架整体不适合Hopper-v4**: 4个Agent一致认为最大熵目标与此环境冲突
2. **DDPG是最可靠的基线**: 所有Agent均从DDPG出发设计新提案
3. **dp_depth的低方差是最有价值信号**: 其自适应n-step机制值得移植
4. **所有自适应熵方法（SAC, attention_prior, value_uncertainty）显著劣于DDPG**: 此结论在p<0.05水平统计显著
5. **0%成功率意味着需要突破性改进**: 增量改进可能不足以从1000跳到2500

### 分歧点

| 问题 | Novel-Academic | Conservative-Academic | Novel-Engineering | Conservative-Engineering |
|------|---------------|---------------------|------------------|------------------------|
| 是否探索全新架构？ | 是（流形约束/滞回切换） | 否（DDPG微调） | 适中（AEN/AH-DDPG） | 否（最简单改动） |
| 基于DDPG还是dp_depth？ | 两者 | DDPG优先 | DDPG+dp_depth融合 | DDPG优先 |
| 是否保留随机策略？ | 混合模式 | 否，确定性 | 否，转向确定 | 否，确定性最好 |

### 提案聚合

| 提案 | 提出者 | 核心思想 | 复杂度 | 预期提升 |
|------|--------|---------|--------|---------|
| AEN-DDPG | Novel-Eng | 自适应探索噪声DDPG | 极低（1行代码） | 1031→~1031,std↓50% |
| Fixed-n DDPG | Cons-Eng | 固定n=3的DDPG | 极低（1行代码） | 1031→~1050 |
| Depth-DDPG | Cons-Acad+Cons-Eng | dp_depth的自适应深度移植DDPG | 低 | 951→~1050,std~50 |
| AD3-H2 | Novel-Acad | 动作维度解耦探索 | 低 | 预期~1100 |
| DDPG-Gate | Cons-Acad | 创新度门控探索 | 中 | 预期~1050 |
| AH-DDPG | Novel-Eng | 自适应时域DDPG | 中 | 预期~1050,std~50 |
| DDPG-EnsembleCritic | Cons-Acad | 深度集成Critic | 中 | 预期~1000 |
| DDPG-SafeReset | Cons-Eng | 安全重置机制 | 中 | 预期~1050,std↓ |
| AEN+AH融合 | Novel-Eng | AEN+AH组合 | 中 | 预期~1080,std~40 |
| IGH-AC | Novel-Acad | 滞回混合模式切换 | 高 | 预期~1100-1200 |
| MCPOE-AC | Novel-Acad | 流形约束正交探索 | 最高 | 理论最优 |

### 推荐执行路径

**Phase 1 (性价比最高)**: AEN-DDPG 或 Fixed-n DDPG
- 1行代码改动，零风险
- 验证"最简单的改进能否接近dp_depth的低方差"

**Phase 2 (稳健改进)**: Depth-DDPG
- 将已验证的dp_depth机制移植到已验证的DDPG框架
- 高概率达到~1050/50 (mean/std)

**Phase 3 (突破性尝试)**: 如果前两阶段成功，启动AD3-H2
- 动作维度解耦是理论最强的方向
- 先在小规模测试(3 seeds, 200k步)验证

### 失败方向（不建议投入）

- ❌ 所有基于SAC框架的改进（LA-SAC, Hessian-SAC, CI-SAC）
- ❌ 所有增加全局熵调节复杂度的方法
- ❌ TD3相关的改进（延迟更新策略在Hopper-v4有害）
- ❌ 需要二阶梯度/Hessian估计的方法（数值不稳定）

---

*讨论记录生成完成 | 2026-06-02*


## Evolution Memory
{
  "last_ide_session": "\u57fa\u4e8e\u6ce8\u610f\u529b\u673a\u5236\u4e0e\u72b6\u6001\u5148\u9a8c\u4e0d\u786e\u5b9a\u6027\u7684\u81ea\u9002\u5e94\u71b5\u8c03\u8282AC\u7b97\u6cd5",
  "top_directions": [
    "\u57fa\u4e8e\u6ce8\u610f\u529b\u673a\u5236\u4e0e\u72b6\u6001\u5148\u9a8c\u4e0d\u786e\u5b9a\u6027\u7684\u81ea\u9002\u5e94\u71b5\u8c03\u8282AC\u7b97\u6cd5",
    "\u57fa\u4e8e\u4ef7\u503c\u5206\u5e03\u5206\u4f4d\u6570\u65b9\u5dee\u7684\u81ea\u9002\u5e94\u71b5\u8c03\u8282AC\u7b97\u6cd5",
    "\u57fa\u4e8e\u5206\u4f4d\u6570\u4ef7\u503c\u65b9\u5dee\u4e0eTD\u8bef\u5dee\u5f02\u65b9\u5dee\u7684\u81ea\u9002\u5e94\u71b5\u8c03\u8282AC\u7b97\u6cd5"
  ],
  "prior_failures": [],
  "best_strategies": [
    "W5: validated=['ATTENTION_PRIOR', 'DDPG', 'DP_DEPTH'], contradicted=[]",
    "W5 validated: ATTENTION_PRIOR, DDPG, DP_DEPTH, GAIT_PHASE, SAC",
    "W5: validated=['ATTENTION_PRIOR', 'DDPG', 'DP_DEPTH'], contradicted=[]"
  ],
  "promising_count": 12,
  "failure_count": 0,
  "strategy_count": 4
}

## 交付物清单
- [ ] artifacts/config.py — 实验配置 (超参数, 随机种子, 数据路径)
- [ ] artifacts/model.py — 模型定义 (网络结构, 层数, 激活函数)
- [ ] artifacts/data.py — 数据加载器 (批处理, 预处理, 增强)
- [ ] artifacts/trainer.py — 训练器 (训练循环, 评估, 日志, checkpoint)
- [ ] artifacts/attention_prior.py — ATTENTION_PRIOR [WEAK] 效果不达预期
- [ ] artifacts/ddpg.py — DDPG [WEAK] 效果不达预期
- [ ] artifacts/dp_depth.py — DP_DEPTH [WEAK] 效果不达预期
- [ ] artifacts/gait_phase.py — GAIT_PHASE [WEAK] 效果不达预期
- [ ] artifacts/refuted.py — REFUTED [WEAK] 效果不达预期
- [ ] artifacts/sac.py — SAC [WEAK] 效果不达预期
- [ ] artifacts/taylor_curvature.py — TAYLOR_CURVATURE [WEAK] 效果不达预期
- [ ] artifacts/td3.py — TD3 [WEAK] 效果不达预期
- [ ] artifacts/td_variance.py — TD_VARIANCE [WEAK] 效果不达预期
- [ ] artifacts/tested.py — TESTED [WEAK] 效果不达预期
- [ ] artifacts/validated.py — VALIDATED [WEAK] 效果不达预期
- [ ] artifacts/value_uncertainty.py — VALUE_UNCERTAINTY [WEAK] 效果不达预期
- [ ] artifacts/基于分位价值方差与td误差异方差的自适应.py — 基于分位价值方差与TD误差异方差的自适应 [RETRY] 上次未完成
- [ ] artifacts/基于分位数价值方差与td误差异方差的自适.py — 基于分位数价值方差与TD误差异方差的自适 [RETRY] 上次未完成
- [ ] artifacts/基于双critic方差分解与注意力状态不.py — 基于双CRITIC方差分解与注意力状态不 [RETRY] 上次未完成
- [ ] artifacts/w2_问题分析.py — AC熵正则化与状态依赖方差调整：Hopper-v4控制改进 [PROPOSED]
- [ ] artifacts/基于值函数不确定性量化的自适应熵调节ac算法.py — 基于值函数不确定性量化的自适应熵调节AC算法 [PROPOSED]
- [ ] artifacts/w3_方案方向.py — 基于动态规划深度与交互熵的混合异方差自适应AC算法 [PROPOSED]
- [ ] artifacts/基于taylor展开的局部熵曲率自适应ac算法.py — 基于Taylor展开的局部熵曲率自适应AC算法 [PROPOSED]
- [ ] artifacts/跨步态相位时序差分噪声驱动的动态熵调节ac算法.py — 跨步态相位时序差分噪声驱动的动态熵调节AC算法 [PROPOSED]
- [ ] artifacts/train_all.py — 一键训练所有算法的 master 脚本
- [ ] artifacts/analyze.py — 结果分析脚本 (学习曲线, 性能对比表, 统计检验)
- [ ] artifacts/smoke_test.py — Smoke test (1 episode, 检查无 NaN/维度错误)

## 规格说明
### artifacts/config.py
- 实验环境配置
- 共享超参数 (seed, batch_size, 优化器设置)
- 各算法专属参数

### artifacts/model.py
- 模型网络定义
- 可配置的层数和激活函数
- 支持常见正则化方法

### artifacts/attention_prior.py
- **上次实验**: Experiment: attention_prior
- CC 记录: {"score_mean": 562.3, "status": "refuted"}

### artifacts/ddpg.py
- **基线算法**: DDPG
- **核心方法**: `def step(self, batch)` — 具体实现见对应的 refined_proposal JSON
- **trainer.py 集成**: BaseAlgorithm ✅ (issubclass 已验证)
- **超参数**: 见 refined_proposals/ddpg.json 或 DomainConfig
- CC 记录: {"score_mean": 1009.6, "status": "validated"}

### artifacts/dp_depth.py
- **上次实验**: Experiment: dp_depth
- CC 记录: {"score_mean": 985.1, "status": "validated"}

### artifacts/gait_phase.py
- **上次实验**: Experiment: gait_phase
- CC 记录: {"score_mean": 967.5, "status": "validated"}

### artifacts/refuted.py
- **上次实验**: Experiment: attention_prior
- CC 记录: {"score_mean": 562.3, "status": "refuted"}

### artifacts/sac.py
- **基线算法**: SAC
- **核心方法**: `def step(self, batch)` — 具体实现见对应的 refined_proposal JSON
- **trainer.py 集成**: BaseAlgorithm ✅ (issubclass 已验证)
- **超参数**: 见 refined_proposals/sac.json 或 DomainConfig
- CC 记录: {"score_mean": 387.6, "status": "refuted"}

### artifacts/taylor_curvature.py
- **上次实验**: Experiment: taylor_curvature
- CC 记录: {"score_mean": 789.6, "status": "validated"}

### artifacts/td3.py
- **基线算法**: TD3
- **核心方法**: `def step(self, batch)` — 具体实现见对应的 refined_proposal JSON
- **trainer.py 集成**: BaseAlgorithm ✅ (issubclass 已验证)
- **超参数**: 见 refined_proposals/td3.json 或 DomainConfig
- CC 记录: {"score_mean": 707.0, "status": "validated"}

### artifacts/td_variance.py
- **上次实验**: Experiment: td_variance
- CC 记录: {"score_mean": 854.5, "status": "validated"}

### artifacts/tested.py
- **上次实验**: Experiment: attention_prior
- CC 记录: {"score_mean": 562.3, "score_std": 0, "n": 2, "status": "tested"}

### artifacts/validated.py
- **上次实验**: Experiment: ddpg
- CC 记录: {"score_mean": 1009.6, "status": "validated"}

### artifacts/value_uncertainty.py
- **上次实验**: Experiment: value_uncertainty
- CC 记录: {"score_mean": 688.8, "status": "refuted"}

### artifacts/基于分位价值方差与td误差异方差的自适应.py
- **算法思路**: ### 伪代码 (PyTorch风格)
```python
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Normal
# === 网络定义 ===
class QuantileQNetwork(nn.Module):
trainer.py 集成: 见 refined_proposals/<atom_id>.json — BaseAlgorithm ✅

### artifacts/基于分位数价值方差与td误差异方差的自适.py
- **算法思路**: ### 伪代码 (PyTorch风格)
```python
# === 算法主循环 ===
for epoch in range(num_epochs):
state = env.reset()
done = False
while not done:
# 从策略网络采样动作
trainer.py 集成: 见 refined_proposals/<atom_id>.json — BaseAlgorithm ✅

### artifacts/基于双critic方差分解与注意力状态不.py
- **算法思路**: ### 伪代码 (PyTorch风格)
```python
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Normal
import numpy as np
# === 网络定义 ===
trainer.py 集成: 见 refined_proposals/<atom_id>.json — BaseAlgorithm ✅

### artifacts/w2_问题分析.py
- 来源: AC熵正则化与状态依赖方差调整：Hopper-v4控制改进
- **摘要**: {"hypothesis": "AC\u7b97\u6cd5\u4e2d\u71b5\u6b63\u5219\u5316\u7cfb\u6570\u56fa\u5b9a\u5bfc\u81f4\u63a2\u7d22\u4e0e\u5229\u7528\u5931\u8861\u662fHopper-v4\u63a7\u5236\u6027\u80fd\u74f6\u9888\uff1b\u57f
trainer.py 集成: BaseAlgorithm ✅ (issubclass 已验证)

### artifacts/基于值函数不确定性量化的自适应熵调节ac算法.py
- 来源: 基于值函数不确定性量化的自适应熵调节AC算法
- **摘要**: {"hypothesis": "AC\u7b97\u6cd5\u4e2d\u56fa\u5b9a\u6216\u5168\u5c40\u71b5\u8c03\u8282\u7cfb\u6570\u65e0\u6cd5\u5e94\u5bf9Hopper-v4\u72b6\u6001\u4f9d\u8d56\u7684\u4e0d\u786e\u5b9a\u6027\uff0c\u5bfc\u81f
trainer.py 集成: BaseAlgorithm ✅ (issubclass 已验证)

### artifacts/w3_方案方向.py
- 来源: 基于动态规划深度与交互熵的混合异方差自适应AC算法
- **摘要**: {"hypothesis": "\u9488\u5bf9Hopper-v4\u4e2d\u5f02\u65b9\u5dee\u52a8\u6001\u5bfc\u81f4\u7684\u63a2\u7d22-\u5229\u7528\u5931\u8861\uff0c\u63d0\u51fa\u4e00\u79cd\u7ed3\u5408\u52a8\u6001\u89c4\u5212\u6df1
trainer.py 集成: BaseAlgorithm ✅ (issubclass 已验证)

### artifacts/基于taylor展开的局部熵曲率自适应ac算法.py
- 来源: 基于Taylor展开的局部熵曲率自适应AC算法
- **摘要**: {"hypothesis": "\u9488\u5bf9Hopper-v4\u5f02\u65b9\u5dee\u52a8\u6001\u5bfc\u81f4\u56fa\u5b9a\u71b5\u7cfb\u6570\u63a2\u7d22-\u5229\u7528\u5931\u8861\uff0c\u63d0\u51fa\u901a\u8fc7\u5c40\u90e8\u71b5\u51fd
trainer.py 集成: BaseAlgorithm ✅ (issubclass 已验证)

### artifacts/跨步态相位时序差分噪声驱动的动态熵调节ac算法.py
- 来源: 跨步态相位时序差分噪声驱动的动态熵调节AC算法
- **摘要**: {"hypothesis": "Hopper-v4\u7684\u5f02\u65b9\u5dee\u6027\u6e90\u4e8e\u6b65\u6001\u5468\u671f\u4e2d\u4e0d\u540c\u76f8\u4f4d\uff08\u817e\u7a7a\u3001\u843d\u5730\u3001\u652f\u6491\uff09\u7684\u52a8\u529b\
trainer.py 集成: BaseAlgorithm ✅ (issubclass 已验证)

### artifacts/train_all.py
- 依次或并行运行所有算法配置
- 每个算法保存独立 checkpoint 和日志
- 支持 --algo 参数只跑指定算法
- 支持 --quick 模式 (减少 timesteps 用于快速验证)

### artifacts/analyze.py
- 读取所有算法日志, 绘制学习曲线
- 输出性能对比表 (mean ± std over seeds)
- Welch's t-test 显著性检验
- 输出 analysis_report.md

## 验收标准
1. smoke_test.py passes (10 episodes, no crash)
2. train_all.py --quick survives 5000 steps
3. Baselines reach known range on benchmark environments
4. At least 1 proposal beats best baseline by >5%
5. analyze.py produces statistical comparison report
