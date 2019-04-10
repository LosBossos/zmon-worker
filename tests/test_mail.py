#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import jinja2
import smtplib

from mock import patch, Mock, ANY

import zmon_worker_monitor.zmon_worker.notifications.mail as m


template_dir = "zmon_worker_monitor/zmon_worker/templates/mail"
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir),
                               trim_blocks=True,
                               lstrip_blocks=True)
alert = {
    'id': 'a1',
    'period': '',
    'name': 'test_alert',
    'check_id': 1,
    'entity': {'id': 'e1'},
    'team': 'ZMON',
    'responsible_team': 'ZMON',
    'notifications': 'notify_mail()',
    'priority': 1,
    'condition': 'value > 1',
}


def test_render_all():
    tmpl = jinja_env.get_template('alert.txt')
    body = tmpl.render(alert_def=alert,
                       captures={'foobar': 4},
                       changed=True,
                       duration=datetime.timedelta(0),
                       entity=alert['entity'],
                       expanded_alert_name=alert['name'],
                       include_captures=True,
                       include_definition=True,
                       include_entity=True,
                       include_value=True,
                       is_alert=True,
                       worker='worker-1',
                       value={'value': 1.0})
    expected = """New alert on e1: test_alert

Current value: 1.0

Worker: worker-1

Captures:
foobar: 4

Alert Definition
Name (ID):     test_alert (ID: a1)
Priority:      1
Check ID:      1
Condition:     value > 1
Team:          ZMON
Resp. Team:    ZMON
Notifications: notify_mail()

Entity
id: e1
"""  # noqa
    assert expected == body


def test_render_capture_only():
    tmpl = jinja_env.get_template('alert.txt')
    body = tmpl.render(alert_def=alert,
                       captures={'foobar': 4},
                       changed=True,
                       duration=datetime.timedelta(0),
                       entity=alert['entity'],
                       expanded_alert_name=alert['name'],
                       include_captures=True,
                       include_definition=False,
                       include_entity=False,
                       include_value=False,
                       is_alert=True,
                       worker='worker-1',
                       value={'value': 1.0})
    expected = """New alert on e1: test_alert


Worker: worker-1

Captures:
foobar: 4


"""  # noqa
    assert expected == body


@patch.object(smtplib, 'SMTP_SSL')
@patch.object(m, 'jinja_env')
def test_send(mock_jinja, mock_smtp):
    m.Mail._config = {
        'notifications.mail.host': 'test_host',
        'notifications.mail.port': 25,
        'notifications.mail.sender': 'test_sender',
        'notifications.mail.on': True,
        'zmon.host': 'https://zmon.example.org'
    }

    alert = {
        'id': 'a1',
        'period': '',
        'name': 'test_alert',
        'notifications': ['send_sms("42", repeat=5)', 'send_mail("test@example.org", repeat=5)'],
        'check_id': 1,
        'entity': {'id': 'e1'},
        'worker': 'worker-1',
    }
    s = Mock()
    mock_smtp.return_value = s
    mock_tmpl = Mock()
    mock_tmpl.render.return_value = ''
    mock_jinja.get_template.return_value = mock_tmpl

    # Regular send
    repeat = m.Mail.notify({
        'captures': {},
        'changed': True,
        'value': {'value': 1.0},
        'entity': {'id': 'e1'},
        'is_alert': True,
        'worker': 'worker-1',
        'alert_def': alert,
        'duration': datetime.timedelta(seconds=0),
    }, 'test@example.org', include_value=False, include_definition=False, include_entity=False)

    assert 0 == repeat

    mock_jinja.get_template.assert_called_with('alert.txt')
    mock_smtp.assert_called_with('test_host', 25)
    s.sendmail.assert_called_with('test_sender', ['test@example.org'], ANY)
    mock_tmpl.render.assert_called_with(alert_def=alert,
                                        captures={},
                                        changed=True,
                                        duration=datetime.timedelta(0),
                                        entity=alert['entity'],
                                        expanded_alert_name=alert['name'],
                                        include_captures=True,
                                        include_definition=False,
                                        include_entity=False,
                                        include_value=False,
                                        is_alert=True,
                                        alert_url='https://zmon.example.org/#/alert-details/a1',
                                        worker='worker-1',
                                        value={'value': 1.0})

    # Send with repeat in HTML
    repeat = m.Mail.notify({
        'captures': {},
        'changed': True,
        'value': {'value': 1.0},
        'entity': {'id': 'e1'},
        'is_alert': True,
        'alert_def': alert,
        'duration': datetime.timedelta(seconds=0),
    }, 'test@example.org', repeat=100, html=True)

    assert 100 == repeat

    mock_jinja.get_template.assert_called_with('alert.html')
    mock_smtp.assert_called_with('test_host', 25)
    s.sendmail.assert_called_with('test_sender', ['test@example.org'], ANY)

    # Exception handling 1: Jinja Error
    mock_smtp.reset_mock()
    s.reset_mock()
    mock_smtp.return_value = s
    mock_jinja.reset_mock()
    t = Mock()
    t.render.side_effect = jinja2.TemplateError('Jinja Error')
    mock_jinja.get_template.return_value = t

    repeat = m.Mail.notify({
        'captures': {},
        'changed': True,
        'value': {'value': 1.0},
        'entity': {'id': 'e1'},
        'is_alert': True,
        'alert_def': alert,
        'duration': datetime.timedelta(seconds=0),
    }, 'test@example.org', repeat=101)

    assert 101 == repeat

    mock_jinja.get_template.assert_called_with('alert.txt')
    assert mock_smtp.called is False

    # Exception handling 2: SMTP Error
    mock_jinja.reset_mock()
    t = Mock()
    t.render.return_value = 'test'
    mock_jinja.get_template.return_value = t
    mock_smtp.reset_mock()
    s = Mock()
    s.sendmail.side_effect = Exception('Error connecting to host')
    mock_smtp.return_value = s

    repeat = m.Mail.notify({
        'captures': {},
        'changed': True,
        'value': {'value': 1.0},
        'entity': {'id': 'e1'},
        'is_alert': True,
        'alert_def': alert,
        'duration': datetime.timedelta(seconds=0),
    }, 'test@example.org', repeat=102)

    assert 102 == repeat

    mock_jinja.get_template.assert_called_with('alert.txt')

    assert mock_smtp.called is True


def test_send_mail_no_change(monkeypatch):
    m.Mail._config = {
        'notifications.mail.host': 'test_host',
        'notifications.mail.port': 25,
        'notifications.mail.sender': 'test_sender',
        'notifications.mail.on': True,
        'zmon.host': 'https://zmon.example.org'
    }

    alert = {
        'alert_def': {'id': 1},
        'alert_changed': False
    }

    r = m.Mail.notify(alert, 'e-1@example.com', cc='some-email@example.org', per_entity=False, repeat=5)

    assert 5 == r
