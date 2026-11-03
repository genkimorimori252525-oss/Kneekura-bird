import unittest
from dataclasses import replace
from uuid import UUID

from ticket_journal import Event, Key, Kind, Model, State

WORLD = UUID('11111111-1111-4111-8111-111111111111')
OWNER = UUID('22222222-2222-4222-8222-222222222222')
ADD = UUID('33333333-3333-4333-8333-333333333333')
REMOVE = UUID('44444444-4444-4444-8444-444444444444')
EPOCH = UUID('55555555-5555-4555-8555-555555555555')
OTHER_EPOCH = UUID('66666666-6666-4666-8666-666666666666')
KEY = Key(WORLD, 'minecraft:overworld', 'wwdebug_benchmark', 'forge-47.4.20', OWNER, -3, 7, False)


class JournalModelTest(unittest.TestCase):
    def event(self, seq, operation, kind, key=KEY):
        return Event(seq, operation, key, kind, EPOCH)

    def run_events(self, *events):
        model = Model(KEY, epoch=EPOCH, assume_exclusive=True)
        for event in events:
            model.accept(event)
        return model

    def add_events(self):
        return [self.event(1, ADD, Kind.ADD_INTENT), self.event(2, ADD, Kind.DURABLE),
                self.event(3, ADD, Kind.DISPATCH), self.event(4, ADD, Kind.RETURN_TRUE)]

    def test_add_requires_observed_durable_intent(self):
        model = self.run_events(self.event(1, ADD, Kind.ADD_INTENT))
        self.assertEqual(model.state, State.ADD_INTENT)
        self.assertIsNone(model.simulated_dispatch())
        model.accept(self.event(2, ADD, Kind.DISPATCH))
        self.assertEqual(model.state, State.UNKNOWN)
        self.assertIsNone(model.simulated_dispatch())

    def test_without_explicit_exclusivity_assumption_no_simulation_is_allowed(self):
        model = Model(KEY, epoch=EPOCH)
        self.assertEqual(model.state, State.UNKNOWN)
        model.accept(self.event(1, ADD, Kind.ADD_INTENT))
        self.assertIsNone(model.simulated_dispatch())

    def test_old_epoch_or_replay_never_reenables_dispatch(self):
        model = Model(KEY, epoch=OTHER_EPOCH, assume_exclusive=True)
        model.accept(self.event(1, ADD, Kind.ADD_INTENT))
        self.assertEqual(model.state, State.UNKNOWN)
        model = Model.after_restart(KEY, epoch=OTHER_EPOCH)
        for event in self.add_events()[:2]:
            model.accept(event)
        self.assertEqual(model.state, State.UNKNOWN)
        self.assertIsNone(model.simulated_dispatch())

    def test_add_durable_dispatch_is_a_hypothetical_not_repeatable_after_dispatch_event(self):
        model = self.run_events(*self.add_events()[:2])
        self.assertEqual(model.simulated_dispatch(), Kind.ADD_INTENT)
        model.accept(self.event(3, ADD, Kind.DISPATCH))
        self.assertIsNone(model.simulated_dispatch())
        model.accept(self.event(4, ADD, Kind.DISPATCH))
        self.assertEqual(model.state, State.UNKNOWN)

    def test_true_is_only_a_volatile_return(self):
        model = self.run_events(*self.add_events())
        self.assertEqual(model.state, State.ADD_RETURNED_VOLATILE)
        self.assertIsNone(model.simulated_dispatch())
        self.assertFalse(model.claims_disk_durability())

    def test_remove_requires_own_durable_intent_and_new_operation(self):
        model = self.run_events(*self.add_events(), self.event(5, REMOVE, Kind.REMOVE_INTENT))
        self.assertIsNone(model.simulated_dispatch())
        model.accept(self.event(6, REMOVE, Kind.DURABLE))
        self.assertEqual(model.simulated_dispatch(), Kind.REMOVE_INTENT)
        model.accept(self.event(7, REMOVE, Kind.DISPATCH))
        model.accept(self.event(8, REMOVE, Kind.RETURN_TRUE))
        self.assertEqual(model.state, State.REMOVE_RETURNED_VOLATILE)
        self.assertFalse(model.claims_disk_durability())
        self.assertIsNone(model.simulated_dispatch())

    def test_false_exception_crash_and_external_owner_are_terminal_unknown(self):
        for kind in (Kind.RETURN_FALSE, Kind.EXCEPTION, Kind.CRASH, Kind.CORRUPT, Kind.EXTERNAL_OWNER, Kind.CONTEXT_UNCERTAIN):
            with self.subTest(kind=kind):
                model = self.run_events(*self.add_events()[:3], self.event(4, ADD, kind))
                self.assertEqual(model.state, State.UNKNOWN)
                model.accept(self.event(5, ADD, Kind.RETURN_TRUE))
                self.assertEqual(model.state, State.UNKNOWN)
                self.assertIsNone(model.simulated_dispatch())

    def test_restart_never_grants_automatic_dispatch_or_release(self):
        for prefix in ([], self.add_events()[:1], self.add_events()[:2], self.add_events()[:3], self.add_events()):
            with self.subTest(events=len(prefix)):
                model = self.run_events(*prefix)
                model.accept(self.event(len(prefix) + 1, ADD, Kind.RESTART))
                self.assertEqual(model.state, State.UNKNOWN)
                self.assertIsNone(model.simulated_dispatch())

    def test_crash_and_partial_exception_at_each_add_or_remove_boundary_halts(self):
        prefixes = [[], self.add_events()[:1], self.add_events()[:2], self.add_events()[:3],
                    self.add_events(), [*self.add_events(), self.event(5, REMOVE, Kind.REMOVE_INTENT)],
                    [*self.add_events(), self.event(5, REMOVE, Kind.REMOVE_INTENT), self.event(6, REMOVE, Kind.DURABLE)],
                    [*self.add_events(), self.event(5, REMOVE, Kind.REMOVE_INTENT), self.event(6, REMOVE, Kind.DURABLE),
                     self.event(7, REMOVE, Kind.DISPATCH)]]
        for prefix in prefixes:
            for kind in (Kind.CRASH, Kind.EXCEPTION):
                with self.subTest(events=len(prefix), kind=kind):
                    operation = REMOVE if len(prefix) >= 5 else ADD
                    model = self.run_events(*prefix, self.event(len(prefix) + 1, operation, kind))
                    self.assertEqual(model.state, State.UNKNOWN)
                    self.assertIsNone(model.simulated_dispatch())

    def test_backend_is_an_opaque_consistency_label_not_version_validation(self):
        key = replace(KEY, backend='unverified-backend')
        model = Model(key, epoch=EPOCH, assume_exclusive=True)
        model.accept(self.event(1, ADD, Kind.ADD_INTENT, key))
        model.accept(self.event(2, ADD, Kind.DURABLE, key))
        self.assertEqual(model.simulated_dispatch(), Kind.ADD_INTENT)
        # A caller must explicitly report that the unverified context is unsafe.
        model.accept(self.event(3, ADD, Kind.CONTEXT_UNCERTAIN, key))
        self.assertEqual(model.state, State.UNKNOWN)

    def test_token_is_immutable_and_context_uncertainty_halts(self):
        with self.assertRaises(AttributeError):
            KEY.chunk_x = 42
        model = self.run_events(self.event(1, ADD, Kind.ADD_INTENT), self.event(2, ADD, Kind.DURABLE),
                                self.event(3, ADD, Kind.CONTEXT_UNCERTAIN))
        self.assertEqual(model.state, State.UNKNOWN)
        self.assertIsNone(model.simulated_dispatch())

    def test_mismatched_world_dimension_version_owner_chunk_ticking_halts(self):
        changed = [replace(KEY, world=UUID('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')),
                   replace(KEY, dimension='minecraft:the_nether'), replace(KEY, mod='other_mod'),
                   replace(KEY, backend='other-version'), replace(KEY, owner=WORLD),
                   replace(KEY, chunk_x=3), replace(KEY, chunk_z=-7), replace(KEY, ticking=True)]
        for key in changed:
            with self.subTest(key=key):
                model = self.run_events(self.event(1, ADD, Kind.ADD_INTENT), self.event(2, ADD, Kind.DURABLE, key))
                self.assertEqual(model.state, State.UNKNOWN)
                self.assertIsNone(model.simulated_dispatch())

    def test_duplicate_gap_reordered_invalid_operation_halts(self):
        for events in ([self.event(2, ADD, Kind.ADD_INTENT)],
                       [self.event(1, ADD, Kind.DURABLE)],
                       [self.event(1, ADD, Kind.ADD_INTENT), self.event(1, ADD, Kind.DURABLE)],
                       [self.event(1, ADD, Kind.ADD_INTENT), self.event(2, REMOVE, Kind.DURABLE)],
                       [*self.add_events(), self.event(5, ADD, Kind.REMOVE_INTENT)],
                       [self.event(1, ADD, Kind.ADD_INTENT), self.event(2, ADD, Kind.DURABLE),
                        self.event(3, ADD, Kind.DISPATCH), self.event(4, ADD, Kind.DISPATCH)]):
            with self.subTest(events=events):
                self.assertEqual(self.run_events(*events).state, State.UNKNOWN)

    def test_malformed_or_non_boolean_ticking_rejected(self):
        for key in (replace(KEY, ticking=1), replace(KEY, chunk_x=True), replace(KEY, dimension=''),
                    replace(KEY, world=None), replace(KEY, owner=None), replace(KEY, backend='')):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    Model(key, epoch=EPOCH, assume_exclusive=True)
        model = Model(KEY, epoch=EPOCH, assume_exclusive=True)
        model.accept(Event(True, ADD, KEY, Kind.ADD_INTENT, EPOCH))
        self.assertEqual(model.state, State.UNKNOWN)

    def test_partial_remove_failure_is_not_success_or_retry(self):
        for failure in (Kind.EXCEPTION, Kind.CRASH, Kind.RETURN_FALSE, Kind.RESTART):
            events = [*self.add_events(), self.event(5, REMOVE, Kind.REMOVE_INTENT),
                      self.event(6, REMOVE, Kind.DURABLE), self.event(7, REMOVE, Kind.DISPATCH),
                      self.event(8, REMOVE, failure)]
            with self.subTest(failure=failure):
                model = self.run_events(*events)
                self.assertEqual(model.state, State.UNKNOWN)
                self.assertIsNone(model.simulated_dispatch())


if __name__ == '__main__':
    unittest.main()
