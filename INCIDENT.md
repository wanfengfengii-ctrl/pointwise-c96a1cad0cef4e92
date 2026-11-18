# 展开费用明细事故

沿用 README.md 的 Python API、计划语法、来源坐标、函数轨迹、错误和发布约定。两条内容相同的来源记录各有两个同值元素。展开后四行都要保留，来源费用编号依次为 1、1、2、2，实际只在各自来源坐标调用 next_ticket 一次。

外层 fee 前向引用同层的 serial；内层另声明同名 serial，并使用外层 fee 加 100。此计划合法，四行的外层费用仍为 1、1、2、2，元素费用为 101、101、102、102。内层同名声明不改变外层表达式的含义。真正的依赖环仍须在登记时拒绝。

运行 python3.11 -B -m tests.test_binding_incident 可查看两种事故的实际和预期明细、调用轨迹或登记错误。业务核对不一致时输出 BINDING_OWNERSHIP_MISMATCH 并退出 1。README.md 的完整测试入口同时运行这两项核对；samples.py 展示现有成功明细、调用与失败后的旧成果读取。

## 根因与修复

根因有两处，均在绑定所有权的归属上：

1. 运行期（warehouse/execution/environments.py）：每个出现环境为“可见的全部绑定”（含祖先绑定）按自身 scope 编号建求值单元。于是每条元素出现都为外层绑定重新分配单元并重复求值（next_ticket 按元素调用而非按来源），父表达式还在后代环境中求值；同名时祖先绑定甚至被合并布局直接覆盖丢失。修复：环境只持有本 scope 声明绑定的单元，子环境经父链共享其真实祖先的单元；引用沿父链找到声明环境，在该环境中求值并缓存，单元按 binding_id（scope_id:名称）标识。输出行改为直接在叶环境的真实声明环境序列（projections）上求值，不再用共享叶单元的拷贝视图。
2. 登记期（warehouse/planning/resolution.py）：resolve_reference 把引用标记为“引用方”而非“声明方”的 scope；validate_row_layout 又在按名称合并的布局上用裸名称建依赖图，内层同名声明把两个不同绑定并成一个节点，虚构出 fee → serial → fee 的环。修复：引用解析记录声明它的词法 scope（内层遮蔽外层）；依赖图改按解析后的 binding_id 建边，同名不同绑定各占节点，合法计划不再被误拒，真实的同层依赖环仍在登记时拒绝。

## 验证

- python3.11 -B -m tests.test_binding_incident：两种情形 matched 均为 true，退出码 0（费用 1、1、2、2 与 101、101、102、102，每个来源坐标各调用一次 next_ticket）。
- python3.11 -B -m unittest discover -s tests -t . -v：34 项全部通过。新增回归 tests/test_execution.py::test_shadowed_binding_keeps_outer_meaning（与 oracle 差分核对遮蔽+前向引用计划的明细与轨迹）和 tests/test_planning.py::test_shadowed_names_keep_cycles_lexical（合法同名计划被接受、祖先引用归属 s0、含遮蔽的同层/自引用真环仍被拒）。
- python3.11 -B samples.py：来源编号按来源复用（1、1、4、4），元素编号按元素出现分配（2、3、5、6），调用坐标真实；失败运行不发布部分成果，旧成功成果仍可按 run_id 读取。
