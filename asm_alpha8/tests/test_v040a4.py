import unittest

from asm import __version__
from asm.planning import ContingentInternalPlanner, ProbabilisticInternalPlanner, StateGoal


class TableDistributionPredictor:
    def __init__(self, table):
        self.table = table
        self.calls = 0

    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
        self.calls += 1
        rows = list(self.table.get((state.get('loc'), action), []))
        outcomes = [
            {
                'predicted_state': {'loc': loc}, 'probability': float(prob),
                'conditional_probability': float(prob), 'support': 100, 'outcome_slot': i,
            }
            for i, (loc, prob) in enumerate(rows[:top_k])
        ]
        mass = sum(x['probability'] for x in outcomes)
        return {
            'mechanism_type': mechanism_type, 'entity_id': entity_id,
            'outcomes': outcomes, 'unknown_probability': max(0.0, 1.0 - mass),
            'support': 100, 'probability_source': 'table', 'calibrated': True,
            '_simulation_context': simulation_context, '_simulation_context_key': '',
        }


def clue_world():
    return {
        ('start', 'sense'): [('clueA', .5), ('clueB', .5)],
        ('start', 'chooseA'): [('goal', .5), ('hazard', .5)],
        ('start', 'chooseB'): [('goal', .5), ('hazard', .5)],
        ('clueA', 'chooseA'): [('goal', 1.0)],
        ('clueA', 'chooseB'): [('hazard', 1.0)],
        ('clueB', 'chooseA'): [('hazard', 1.0)],
        ('clueB', 'chooseB'): [('goal', 1.0)],
    }


class ContingentPlanningTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_useful_information_builds_contingent_policy(self):
        predictor = TableDistributionPredictor(clue_world())
        planner = ContingentInternalPlanner(
            predictor, max_horizon=2, max_expansions=64,
            min_goal_probability=.95, max_hazard_probability=.05,
            max_unknown_probability=.05, risk_aversion=4.0,
        )
        plan = planner.plan(
            'clue', entity_id='x', initial_state={'loc': 'start'},
            actions=('sense', 'chooseA', 'chooseB'),
            goal=StateGoal({'loc': 'goal'}, {'loc': 'hazard'}), horizon=2,
        )
        self.assertEqual(plan['status'], 'contingent_plan_found')
        self.assertEqual(plan['best']['action'], 'sense')
        self.assertAlmostEqual(plan['best']['goal_probability'], 1.0)
        self.assertAlmostEqual(plan['best']['hazard_probability'], 0.0)
        branch_actions = {
            b['observation']['loc']: b['policy']['action'] for b in plan['best']['branches']
        }
        self.assertEqual(branch_actions, {'clueA': 'chooseA', 'clueB': 'chooseB'})
        self.assertTrue(plan['contingent_branching_used'])
        self.assertGreater(plan['contingency_gain'], 0.4)

    def test_alpha3_open_loop_control_cannot_solve_clue_world(self):
        predictor = TableDistributionPredictor(clue_world())
        planner = ProbabilisticInternalPlanner(
            predictor, max_horizon=2, beam_width=8, max_expansions=64,
            min_goal_probability=.95, max_hazard_probability=.05,
            max_unknown_probability=.05, risk_aversion=4.0,
        )
        plan = planner.plan(
            'clue', entity_id='x', initial_state={'loc': 'start'},
            actions=('sense', 'chooseA', 'chooseB'),
            goal=StateGoal({'loc': 'goal'}, {'loc': 'hazard'}), horizon=2,
        )
        self.assertNotEqual(plan['status'], 'risk_aware_plan_found')
        self.assertLessEqual(plan['best']['goal_probability'], .5 + 1e-12)

    def test_useless_information_is_rejected(self):
        table = {
            ('start', 'go'): [('goal', 1.0)],
            ('start', 'sense'): [('clueA', .5), ('clueB', .5)],
            ('clueA', 'go'): [('goal', 1.0)],
            ('clueB', 'go'): [('goal', 1.0)],
        }
        planner = ContingentInternalPlanner(
            TableDistributionPredictor(table), max_horizon=2, max_expansions=64,
            min_goal_probability=.95, max_hazard_probability=.05,
            max_unknown_probability=.05, cost_weight=.1,
        )
        plan = planner.plan(
            'clue', entity_id='x', initial_state={'loc': 'start'},
            actions=('sense', 'go'), goal=StateGoal({'loc': 'goal'}),
            action_costs={'sense': 1.0, 'go': 0.1}, horizon=2,
        )
        self.assertEqual(plan['best']['action'], 'go')
        self.assertFalse(plan['contingent_branching_used'])
        self.assertAlmostEqual(plan['contingency_gain'], 0.0, places=9)

    def test_branch_risk_is_aggregated(self):
        table = clue_world()
        table[('clueA', 'chooseA')] = [('goal', .95), ('hazard', .05)]
        planner = ContingentInternalPlanner(
            TableDistributionPredictor(table), max_horizon=2, max_expansions=64,
            min_goal_probability=.9, max_hazard_probability=.03,
            max_unknown_probability=.05, risk_aversion=4.0,
        )
        plan = planner.plan(
            'clue', entity_id='x', initial_state={'loc': 'start'},
            actions=('sense', 'chooseA', 'chooseB'),
            goal=StateGoal({'loc': 'goal'}, {'loc': 'hazard'}), horizon=2,
        )
        self.assertEqual(plan['best']['action'], 'sense')
        self.assertAlmostEqual(plan['best']['goal_probability'], .975)
        self.assertAlmostEqual(plan['best']['hazard_probability'], .025)

    def test_unknown_mass_is_preserved(self):
        table = {('start', 'probe'): [('a', .3), ('b', .3)]}
        planner = ContingentInternalPlanner(
            TableDistributionPredictor(table), max_horizon=1, max_expansions=8,
            max_unknown_probability=.5,
        )
        plan = planner.plan(
            'unknown', entity_id='x', initial_state={'loc': 'start'}, actions=('probe',),
            goal=StateGoal({'loc': 'goal'}), horizon=1,
        )
        self.assertAlmostEqual(plan['best']['unknown_probability'], .4)

    def test_budget_is_bounded(self):
        planner = ContingentInternalPlanner(
            TableDistributionPredictor(clue_world()), max_horizon=4,
            max_expansions=3, min_goal_probability=.95,
        )
        plan = planner.plan(
            'clue', entity_id='x', initial_state={'loc': 'start'},
            actions=('sense', 'chooseA', 'chooseB'),
            goal=StateGoal({'loc': 'goal'}, {'loc': 'hazard'}), horizon=4,
        )
        self.assertLessEqual(plan['expansions'], 3)

    def test_action_costs_flow_through_branches(self):
        planner = ContingentInternalPlanner(
            TableDistributionPredictor(clue_world()), max_horizon=2,
            max_expansions=64, min_goal_probability=.95,
            max_hazard_probability=.05, max_unknown_probability=.05,
        )
        plan = planner.plan(
            'clue', entity_id='x', initial_state={'loc': 'start'},
            actions=('sense', 'chooseA', 'chooseB'),
            goal=StateGoal({'loc': 'goal'}, {'loc': 'hazard'}),
            action_costs={'sense': 2.0, 'chooseA': 1.0, 'chooseB': 3.0}, horizon=2,
        )
        # 2 + .5*1 + .5*3 = 4
        self.assertAlmostEqual(plan['best']['expected_cost'], 4.0)

    def test_no_hardcoded_sense_name(self):
        table = clue_world()
        renamed = {}
        for (state, action), outcomes in table.items():
            renamed[(state, 'inspect' if action == 'sense' else action)] = outcomes
        planner = ContingentInternalPlanner(
            TableDistributionPredictor(renamed), max_horizon=2, max_expansions=64,
            min_goal_probability=.95, max_hazard_probability=.05,
            max_unknown_probability=.05, risk_aversion=4.0,
        )
        plan = planner.plan(
            'clue', entity_id='x', initial_state={'loc': 'start'},
            actions=('inspect', 'chooseA', 'chooseB'),
            goal=StateGoal({'loc': 'goal'}, {'loc': 'hazard'}), horizon=2,
        )
        self.assertEqual(plan['best']['action'], 'inspect')
        self.assertTrue(plan['contingent_branching_used'])

    def test_deep_contingency_detected_below_shared_intermediate_action(self):
        table = {
            ('start','sense1'):[('red',.5),('blue',.5)],
            ('red','sense2'):[('redA',.5),('redB',.5)],
            ('blue','sense2'):[('blueA',.5),('blueB',.5)],
            ('redA','a'):[('goal',1.0)], ('redA','b'):[('hazard',1.0)],
            ('redB','a'):[('hazard',1.0)], ('redB','b'):[('goal',1.0)],
            ('blueA','a'):[('goal',1.0)], ('blueA','b'):[('hazard',1.0)],
            ('blueB','a'):[('hazard',1.0)], ('blueB','b'):[('goal',1.0)],
        }
        planner = ContingentInternalPlanner(
            TableDistributionPredictor(table), max_horizon=3, max_expansions=128,
            min_goal_probability=.95, max_hazard_probability=.05,
            max_unknown_probability=.05, risk_aversion=4.0,
        )
        plan = planner.plan(
            'deep', entity_id='x', initial_state={'loc':'start'},
            actions=('sense1','sense2','a','b'),
            goal=StateGoal({'loc':'goal'},{'loc':'hazard'}), horizon=3,
        )
        self.assertEqual(plan['best']['action'], 'sense1')
        self.assertAlmostEqual(plan['best']['goal_probability'], 1.0)
        self.assertTrue(plan['contingent_branching_used'])
        self.assertGreaterEqual(plan['policy_nodes'], 7)



if __name__ == '__main__':
    unittest.main()
