# Copyright 2017 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import date, timedelta
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests import common


@tagged("post_install", "-at_install")
class TestJournalLockDate(common.AccountTestInvoicingCommon):
    def setUp(self):
        super().setUp()
        self.account_move_obj = self.env["account.move"]
        self.account_move_line_obj = self.env["account.move.line"]
        self.company_id = self.ref("base.main_company")
        self.partner = self.browse_ref("base.res_partner_12")

        self.account = self.company_data["default_account_revenue"]
        self.account2 = self.company_data["default_account_expense"]
        self.journal = self.company_data["default_journal_bank"]

        # lock journal, set 'Lock Date for Non-Advisers'
        self.lock_date = date.today()
        self.journal.period_lock_date = self.lock_date

        self.journal = self.env["account.journal"].create(
            {"name": "Test Journal", "type": "general", "code": "TEST"}
        )
        self.wizard = self.env["update.journal.lock.dates.wizard"].create(
            {
                "period_lock_date": date.today(),
                "fiscalyear_lock_date": date.today(),
            }
        )

    def test_journal_lock_date(self):
        # Temporarily assign the Invoicing/Administrator group to the test user
        self.env.user.write(
            {"groups_id": [Command.link(self.ref("account.group_account_manager"))]}
        )

        # Ensure the journal lock date is correctly set
        self.journal.period_lock_date = self.lock_date
        self.assertEqual(self.journal.period_lock_date, self.lock_date)

        # Ensure proper sequence configuration for the journal
        sequence = self.env["ir.sequence"].create(
            {
                "name": f"Test sequence - {self.journal.name}",
                "implementation": "no_gap",
                "padding": 4,
                "number_increment": 1,
                "prefix": "TEST/%(year)s/",
            }
        )

        # Update the journal's sequence
        self.journal.sequence = sequence

        # Remove the group to simulate restricted access for subsequent tests
        self.env.user.write(
            {"groups_id": [Command.unlink(self.ref("account.group_account_manager"))]}
        )
        self.assertFalse(self.env.user.has_group("account.group_account_manager"))

        # Test that a new move cannot be created on lock date
        with self.assertRaisesRegex(
            UserError, ".*prior to and inclusive of the lock date.*"
        ):
            move = self.account_move_obj.create(
                {
                    "date": self.lock_date,
                    "journal_id": self.journal.id,
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": self.account.id,
                                "credit": 1000.0,
                                "name": "Credit line",
                            },
                        ),
                        Command.create(
                            {
                                "account_id": self.account2.id,
                                "debit": 1000.0,
                                "name": "Debit line",
                            },
                        ),
                    ],
                }
            )
            move.action_post()

        def patched_get_chains(self, **kwargs):
            return []

        # Use patch as a context manager as you're doing now
        with patch.object(
            type(self.account_move_obj), "_get_chains_to_hash", patched_get_chains
        ):
            # Create and post move2
            move2 = self.account_move_obj.create(
                {
                    "date": self.lock_date + timedelta(days=3),
                    "journal_id": self.journal.id,
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": self.account.id,
                                "credit": 1000.0,
                                "name": "Credit line",
                            },
                        ),
                        Command.create(
                            {
                                "account_id": self.account2.id,
                                "debit": 1000.0,
                                "name": "Debit line",
                            },
                        ),
                    ],
                }
            )
            # Post with no gap check
            move2.with_context(check_move_sequence_no_gap=False).action_post()

            # Force create move in a lock date
            move3 = self.account_move_obj.with_context(
                bypass_journal_lock_date=True,
                check_move_sequence_no_gap=False,
            ).create(
                {
                    "date": self.lock_date,
                    "journal_id": self.journal.id,
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": self.account.id,
                                "credit": 1000.0,
                                "name": "Credit line",
                            },
                        ),
                        Command.create(
                            {
                                "account_id": self.account2.id,
                                "debit": 1000.0,
                                "name": "Debit line",
                            },
                        ),
                    ],
                }
            )
            move3.action_post()

    def test_check_execute_allowed_adviser(self):
        """Ensure the `_check_execute_allowed` method works for advisers."""
        self.env.user.write(
            {"groups_id": [Command.link(self.ref("account.group_account_manager"))]}
        )
        self.wizard._check_execute_allowed()

    def test_check_execute_allowed_no_permission(self):
        """Ensure the `_check_execute_allowed`
        method raises UserError for non-advisers."""
        self.env.user.write(
            {"groups_id": [Command.unlink(self.ref("account.group_account_manager"))]}
        )
        with self.assertRaises(UserError):
            self.wizard._check_execute_allowed()

    def test_action_update_lock_dates(self):
        """Test the `action_update_lock_dates` method."""
        # Simulate the context with active_ids
        self.env.context = {"active_ids": [self.journal.id]}
        self.wizard.action_update_lock_dates()

        # Check if the dates are updated correctly
        self.assertEqual(self.journal.period_lock_date, self.wizard.period_lock_date)
        self.assertEqual(
            self.journal.fiscalyear_lock_date, self.wizard.fiscalyear_lock_date
        )

    def test_action_update_lock_dates_with_active_ids(self):
        """Test the `action_update_lock_dates` method with active_ids."""
        self.env.context = {"active_ids": [self.journal.id]}

        self.env.user.write(
            {"groups_id": [Command.link(self.ref("account.group_account_manager"))]}
        )

        self.wizard.action_update_lock_dates()

        self.assertEqual(self.journal.period_lock_date, self.wizard.period_lock_date)
        self.assertEqual(
            self.journal.fiscalyear_lock_date, self.wizard.fiscalyear_lock_date
        )

    def test_action_update_lock_dates_no_active_ids(self):
        """Test the `action_update_lock_dates` method without active_ids."""
        self.env.context = {}

        self.env.user.write(
            {"groups_id": [Command.link(self.ref("account.group_account_manager"))]}
        )

        self.wizard.action_update_lock_dates()

        self.assertNotEqual(self.journal.period_lock_date, self.wizard.period_lock_date)
        self.assertNotEqual(
            self.journal.fiscalyear_lock_date, self.wizard.fiscalyear_lock_date
        )

    def test_check_fiscal_lock_dates_adviser(self):
        """Test `_check_fiscal_lock_dates` for an adviser user."""
        # Assign the Invoicing/Administrator group to the test user
        self.env.user.write(
            {"groups_id": [Command.link(self.ref("account.group_account_manager"))]}
        )

        # Set up a fiscal year lock date on the journal
        self.journal.fiscalyear_lock_date = self.lock_date

        # Create a move with a date before the lock date
        move = self.account_move_obj.create(
            {
                "date": self.lock_date - timedelta(days=1),
                "journal_id": self.journal.id,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.account.id,
                            "credit": 1000.0,
                            "name": "Credit line",
                        },
                    ),
                    Command.create(
                        {
                            "account_id": self.account2.id,
                            "debit": 1000.0,
                            "name": "Debit line",
                        },
                    ),
                ],
            }
        )

        # Call `_check_fiscal_lock_dates` and verify that a UserError is raised
        with self.assertRaisesRegex(
            UserError, "You cannot add/modify entries for the journal"
        ):
            move._check_fiscal_lock_dates()

        # Verify that the exact message for advisers is shown
        try:
            move._check_fiscal_lock_dates()
        except UserError as e:
            self.assertIn("You cannot add/modify entries for the journal", str(e))
            self.assertIn("prior to and inclusive of the lock date", str(e))

    def test_check_fiscal_lock_dates_non_adviser(self):
        """Test `_check_fiscal_lock_dates` with a non-adviser user."""
        self.env.user.write(
            {"groups_id": [Command.link(self.ref("account.group_account_manager"))]}
        )

        self.journal.period_lock_date = self.lock_date

        self.env.user.write(
            {"groups_id": [Command.unlink(self.ref("account.group_account_manager"))]}
        )
        self.assertFalse(self.env.user.has_group("account.group_account_manager"))

        move = self.account_move_obj.create(
            {
                "date": self.lock_date - timedelta(days=1),
                "journal_id": self.journal.id,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.account.id,
                            "credit": 1000.0,
                            "name": "Credit line",
                        },
                    ),
                    Command.create(
                        {
                            "account_id": self.account2.id,
                            "debit": 1000.0,
                            "name": "Debit line",
                        },
                    ),
                ],
            }
        )

        with self.assertRaisesRegex(
            UserError, "You cannot add/modify entries for the journal"
        ):
            move._check_fiscal_lock_dates()
