from warehouse.execution.bindings import BindingCell
from warehouse.source.coordinates import OccurrenceCoordinate, child_coordinate
from warehouse.expressions.errors import BindingCycleError, ErrorLocation


class _EmptySide:
    pass


EMPTY_SIDE = _EmptySide()


class Environment:
    """Per-occurrence evaluation environment.

    An environment owns demand cells only for the bindings declared by its
    own scope: every source occurrence owns independent root cells and every
    element occurrence owns independent child cells. Descendants reach their
    actual ancestors' cells through the parent chain, so an ancestor binding
    is evaluated at most once per ancestor occurrence, in the ancestor's own
    environment (its own coordinate, data and aliases), and is never
    re-allocated per descendant. Equal-valued occurrences never share cells.
    """

    def __init__(self, scope, coordinate, root_record, aliases=None,
                 parent=None, projections=()):
        self.scope = scope
        self.coordinate = coordinate
        self.root_record = root_record
        self.aliases = {} if aliases is None else aliases
        self.parent = parent
        # Projection lineage: this environment and its ancestors, outermost
        # first. Outputs evaluate per retained leaf against these actual
        # declaration environments.
        self.projections = projections + (self,)
        self.bindings = {b.binding_id: b for b in scope.bindings}
        self.cells = {binding_id: BindingCell() for binding_id in self.bindings}

    @classmethod
    def root(cls, scope, source, record):
        return cls(scope, OccurrenceCoordinate(source), record)

    def child(self, scope, alias, element, index):
        coordinate = child_coordinate(self.coordinate, scope.scope_id, index)
        return Environment(scope, coordinate, self.root_record,
                           self.aliases | {alias: element}, self, self.projections)

    def resolve_binding(self, reference, context, demand_coordinate):
        from warehouse.expressions.semantics import evaluate_expression
        environment = self
        while environment is not None:
            binding = environment.bindings.get(reference.binding_id)
            if binding is not None:
                # The owning environment evaluates and caches the binding;
                # the first demander's coordinate is kept for the location.
                return environment.cells[reference.binding_id].demand(
                    lambda: evaluate_expression(
                        binding.expr, environment, context, demand_coordinate),
                    ErrorLocation(binding.expr.location, demand_coordinate))
            environment = environment.parent
        raise BindingCycleError(f'unknown row binding {reference.name}')

    def read_base(self, name):
        if name == 'root':
            return self.root_record
        if name not in self.aliases:
            raise BindingCycleError(f'no field base {name}')
        return self.aliases[name]
