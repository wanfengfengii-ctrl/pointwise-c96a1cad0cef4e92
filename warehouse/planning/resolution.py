from dataclasses import dataclass, replace
from warehouse.expressions.model import BindingReference
from warehouse.expressions.validation import collect_binding_references
from warehouse.planning.model import PlanValidationError, ScopeDefinition


@dataclass
class ScopeTable:
    scope_id: str
    names: frozenset
    aliases: frozenset
    parent: object = None
    child: object = None


def build_scope_table(root):
    next_scope = 0

    def build(scope, parent=None, aliases=frozenset({'root'})):
        nonlocal next_scope
        table = ScopeTable(f's{next_scope}', frozenset(b.name for b in scope.bindings),
                           aliases, parent)
        next_scope += 1
        if scope.expand:
            table.child = build(scope.expand.scope, table, aliases | {scope.expand.alias})
        return table

    return build(root)


def resolve_reference(name, table):
    current = table
    while current is not None:
        if name in current.names:
            # The reference is owned by the scope that declares the name
            # (innermost lexical match), not by the referring scope.
            return BindingReference(f'{current.scope_id}:{name}', current.scope_id, name)
        current = current.parent
    raise PlanValidationError(f'{table.scope_id}: unknown binding {name}')


def validate_row_layout(layout, scope_id):
    # layout maps binding_id -> BindingDefinition for the whole scope chain.
    # Cycle detection runs on resolved binding identities: a shadowed
    # ancestor binding keeps its own node, so an inner declaration that
    # reuses an ancestor's name cannot fabricate a cycle, while genuine
    # same-scope dependency cycles are still rejected here.
    graph = {binding_id: [ref.binding_id
                          for ref in collect_binding_references(binding.expr)]
             for binding_id, binding in layout.items()}
    done, active = set(), set()

    def check(binding_id):
        if binding_id in active:
            raise PlanValidationError(
                f'binding dependency cycle at {scope_id}:{layout[binding_id].name}')
        if binding_id in done:
            return
        active.add(binding_id)
        for target in graph[binding_id]:
            check(target)
        active.remove(binding_id)
        done.add(binding_id)

    for binding_id in graph:
        check(binding_id)


def resolve_plan(plan):
    tables = build_scope_table(plan.root)

    def expression(expr, table):
        value = expr.value
        if expr.op == 'ref':
            value = resolve_reference(value, table)
        if expr.op == 'field' and value.base not in table.aliases:
            raise PlanValidationError(f'{expr.location}: unknown field base {value.base}')
        return replace(expr, value=value,
                       args=tuple(expression(arg, table) for arg in expr.args))

    def scope(node, table, inherited):
        bindings = tuple(replace(b, expr=expression(b.expr, table),
                                 binding_id=f'{table.scope_id}:{b.name}',
                                 owner_scope=table.scope_id) for b in node.bindings)
        layout = inherited | {binding.binding_id: binding for binding in bindings}
        validate_row_layout(layout, table.scope_id)
        outputs = tuple(replace(o, expr=expression(o.expr, table)) for o in node.output)
        expand = None
        if node.expand:
            expand = replace(node.expand, expr=expression(node.expand.expr, table),
                             scope=scope(node.expand.scope, table.child, layout))
        return ScopeDefinition(bindings,
                               expression(node.where, table) if node.where else None,
                               expand, outputs, table.scope_id, tuple(layout.values()))

    return scope(plan.root, tables, {})
