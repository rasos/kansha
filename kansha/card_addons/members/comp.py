#--
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

from nagare.i18n import _
from peak.rules import when
from nagare.security import common
from nagare import component, security, log

from kansha import exceptions
from kansha.toolbox import overlay
from kansha.user import usermanager
from kansha.board.comp import Board
from kansha.cardextension import CardExtension
from kansha.services.actionlog.messages import render_event

from .models import DataMembership


# TODO: move this to board extension
@when(common.Rules.has_permission, "user and perm == 'Add Users' and isinstance(subject, Board)")
def has_permission_Board_add_users(self, user, perm, board):
    """Test if users is one of the board's managers, if he is he can add new user to the board"""
    return board.has_manager(user)


@when(render_event, "action=='card_add_member'")
def render_event_card_add_member(action, data):
    return _(u'User %(user)s has been assigned to card "%(card)s"') % data


@when(render_event, "action=='card_remove_member'")
def render_event_card_remove_member(action, data):
    return _(u'User %(user)s has been unassigned from card "%(card)s"') % data


class CardMembers(CardExtension):

    LOAD_PRIORITY = 90

    MAX_SHOWN_MEMBERS = 3

    def __init__(self, card, action_log, configurator):
        """
        Card is a card business object.
        """

        super(CardMembers, self).__init__(card, action_log, configurator)

        # members part of the card
        self.overlay_add_members = component.Component(
            overlay.Overlay(lambda r: (r.i(class_='ico-btn icon-user'), r.span(_(u'+'), class_='count')),
                            lambda r: component.Component(self).render(r, model='add_member_overlay'), dynamic=True, cls='card-overlay'))
        self.new_member = component.Component(usermanager.NewMember(self.autocomplete_method), model='add_members')
        self.members = [component.Component(usermanager.UserManager.get_app_user(data=membership.user))
                        for membership in DataMembership.get_for_card(self.card.data)]

        self.see_all_members = component.Component(
            overlay.Overlay(lambda r: component.Component(self).render(r, model='more_users'),
                            lambda r: component.Component(self).on_answer(self.remove_member).render(r, model='members_list_overlay'),
                            dynamic=False, cls='card-overlay'))
        self._favorites = []

    def autocomplete_method(self, value):
        """ """
        available_user_ids = self.get_available_user_ids()
        return [u for u in usermanager.UserManager.search(value) if u.id in available_user_ids]

    def get_available_user_ids(self):
        """Return ids of users who are authorized to be added on this card

        Return:
            - a set of ids
        """
        return self.get_all_available_user_ids() | self.get_pending_user_ids() - set(user().id for user in self.members)

    def get_all_available_user_ids(self):
        return self.configurator.get_available_user_ids() if self.configurator else []

    def get_pending_user_ids(self):
        return self.configurator.get_pending_user_ids() if self.configurator else []

    @property
    def favorites(self):
        """Return favorites users for a given card

        Return:
            - list of favorites (User instances) wrapped in component
        """

        # to be optimized later if still exists
        member_usernames = set(member().username for member in self.members)
        # Take the 5 most popular that are not already affected to this card
        favorites = [userdata for userdata in DataMembership.favorites_for(self.card.data)
                     if userdata.username not in member_usernames]

        # store component for callback lookup
        self._favorites = [component.Component(usermanager.UserManager.get_app_user(data=userdata), "friend")
                           for userdata in favorites[:5]]
        return self._favorites

    def add_members(self, emails):
        """Add new members from emails

        In:
            - ``emails`` -- list of strings
        """

        memberships = DataMembership.add_members_from_emails(self.card.data, emails)

        for member in (usermanager.UserManager.get_app_user(data=ms.user) for ms in memberships):
            values = {'user_id': member.username, 'user': member.fullname, 'card': self.card.get_title()}
            self.action_log.add_history(security.get_user(), u'card_add_member', values)
            self.members.append(component.Component(member))

    def remove_member(self, username):
        """Remove member username from card member"""
        DataMembership.remove_member(self.card.data, username)
        for member in self.members:
            if member().username == username:
                self.members.remove(member)
                values = {'user_id': member().username, 'user': member().data.fullname,
                          'card': self.card.get_title()}
                self.action_log.add_history(security.get_user(), u'card_remove_member', values)
                break

    def has_permission_on_card(self, user, perm):
        granted = True
        if perm == 'edit':
            granted = user and (user.id in self.get_all_available_user_ids())
        return granted
