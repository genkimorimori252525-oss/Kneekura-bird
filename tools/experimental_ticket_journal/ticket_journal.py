"""Pure simulation only: no Forge, world, journal storage or side effects."""
from dataclasses import dataclass
from enum import Enum, auto
from uuid import UUID


class Kind(Enum):
    ADD_INTENT = auto()
    REMOVE_INTENT = auto()
    DURABLE = auto()
    DISPATCH = auto()
    RETURN_TRUE = auto()
    RETURN_FALSE = auto()
    EXCEPTION = auto()
    CRASH = auto()
    CORRUPT = auto()
    EXTERNAL_OWNER = auto()
    CONTEXT_UNCERTAIN = auto()
    RESTART = auto()


class State(Enum):
    NEW = auto()
    ADD_INTENT = auto()
    ADD_DURABLE = auto()
    ADD_DISPATCHED = auto()
    ADD_RETURNED_VOLATILE = auto()
    REMOVE_INTENT = auto()
    REMOVE_DURABLE = auto()
    REMOVE_DISPATCHED = auto()
    REMOVE_RETURNED_VOLATILE = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class Key:
    world: UUID
    dimension: str
    mod: str
    backend: str
    owner: UUID
    chunk_x: int
    chunk_z: int
    ticking: bool

    def valid(self):
        return (type(self.world) is UUID and self.world.int != 0
                and type(self.owner) is UUID and self.owner.int != 0
                and all(type(s) is str and 0 < len(s) <= 256 and s == s.strip()
                        for s in (self.dimension, self.mod, self.backend))
                and type(self.chunk_x) is int and -(2**31) <= self.chunk_x < 2**31
                and type(self.chunk_z) is int and -(2**31) <= self.chunk_z < 2**31
                and type(self.ticking) is bool)


@dataclass(frozen=True)
class Event:
    sequence: int
    operation: UUID
    key: Key
    kind: Kind
    epoch: UUID


class Model:
    """One key and one uninterrupted simulated process. UNKNOWN is absorbing."""
    def __init__(self, key, *, epoch, assume_exclusive=False):
        if (type(key) is not Key or not key.valid() or type(epoch) is not UUID
                or epoch.int == 0 or type(assume_exclusive) is not bool):
            raise ValueError('invalid key, epoch or assumption')
        self._key = key
        self._epoch = epoch
        # A hypothetical assumption, never evidence that the owner is exclusive.
        self._state = State.NEW if assume_exclusive else State.UNKNOWN
        self._next = 1
        self._operation = None
        self._seen = set()

    @classmethod
    def after_restart(cls, key, *, epoch):
        # No stored history proves the old Forge call did or did not happen.
        return cls(key, epoch=epoch, assume_exclusive=False)

    @property
    def state(self):
        return self._state

    def simulated_dispatch(self):
        """Hypothetical next event only; never an authorization for real I/O."""
        if self._state is State.ADD_DURABLE:
            return Kind.ADD_INTENT
        if self._state is State.REMOVE_DURABLE:
            return Kind.REMOVE_INTENT
        return None

    def claims_disk_durability(self):
        return False

    def accept(self, event):
        if self._state is State.UNKNOWN:
            return
        if (type(event) is not Event or type(event.sequence) is not int
                or event.sequence != self._next or type(event.operation) is not UUID
                or event.operation.int == 0 or type(event.key) is not Key
                or not event.key.valid() or event.key != self._key or type(event.kind) is not Kind
                or type(event.epoch) is not UUID or event.epoch != self._epoch):
            self._state = State.UNKNOWN
            return
        self._next += 1
        if event.kind in (Kind.RETURN_FALSE, Kind.EXCEPTION, Kind.CRASH,
                          Kind.CORRUPT, Kind.EXTERNAL_OWNER, Kind.CONTEXT_UNCERTAIN, Kind.RESTART):
            self._state = State.UNKNOWN
            return
        if event.kind in (Kind.ADD_INTENT, Kind.REMOVE_INTENT):
            expected = State.NEW if event.kind is Kind.ADD_INTENT else State.ADD_RETURNED_VOLATILE
            if self._state is not expected or event.operation in self._seen:
                self._state = State.UNKNOWN
                return
            self._seen.add(event.operation)
            self._operation = event.operation
            self._state = State.ADD_INTENT if event.kind is Kind.ADD_INTENT else State.REMOVE_INTENT
            return
        if event.operation != self._operation:
            self._state = State.UNKNOWN
            return
        transitions = {
            (State.ADD_INTENT, Kind.DURABLE): State.ADD_DURABLE,
            (State.ADD_DURABLE, Kind.DISPATCH): State.ADD_DISPATCHED,
            (State.ADD_DISPATCHED, Kind.RETURN_TRUE): State.ADD_RETURNED_VOLATILE,
            (State.REMOVE_INTENT, Kind.DURABLE): State.REMOVE_DURABLE,
            (State.REMOVE_DURABLE, Kind.DISPATCH): State.REMOVE_DISPATCHED,
            (State.REMOVE_DISPATCHED, Kind.RETURN_TRUE): State.REMOVE_RETURNED_VOLATILE,
        }
        self._state = transitions.get((self._state, event.kind), State.UNKNOWN)
