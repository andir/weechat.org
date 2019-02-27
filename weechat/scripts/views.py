# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2019 Sébastien Helleu <flashcode@flashtux.org>
#
# This file is part of WeeChat.org.
#
# WeeChat.org is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# WeeChat.org is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with WeeChat.org.  If not, see <https://www.gnu.org/licenses/>.
#

"""Views for "scripts" menu."""

from datetime import datetime
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

from django.conf import settings
from django.core.mail import EmailMessage
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404

from weechat.common.path import files_path_join
from weechat.download.models import Release
from weechat.scripts.models import (
    Script,
    ScriptFormAdd,
    ScriptFormUpdate,
    get_language_from_extension,
)

API_OLD = '0.2.6'
API_STABLE = '0.3.0'

# list of keys that are sorted by default using descending order
KEY_ORDER_BY_DESC = ['popularity', 'min_weechat', 'max_weechat', 'added',
                     'updated']

PYGMENTS_LEXER = {
    'pl': 'perl',
    'py': 'python',
    'rb': 'ruby',
    'lua': 'lua',
    'tcl': 'tcl',
    'scm': 'scheme',
    'js': 'javascript',
    'php': 'php',
}


def get_sort_key(sort_key):
    """Get sort keys to sort scripts (in SQL request)."""
    keys = sort_key.split(',')
    if 'name' not in keys:
        keys.append('name')
    for i, key in enumerate(keys):
        if key in KEY_ORDER_BY_DESC:
            keys[i] = '-%s' % key
    return keys


def get_highlighted_source(source, language):
    """Get source highlighted with pygments."""
    return highlight(source,
                     get_lexer_by_name(language, stripnl=True,
                                       encoding='utf-8'),
                     HtmlFormatter(cssclass='pygments', linenos='table'))


def scripts(request, api='stable', sort_key='popularity', filter_name='',
            filter_value=''):
    """Page with list of scripts."""

    def sort_by_popularity(item):
        return (-1 * item[1], item[0].lower())

    def sort_by_name(item):
        return item[0].lower()

    if api == 'legacy':
        script_list = (Script.objects.filter(visible=1)
                       .filter(max_weechat=API_OLD)
                       .order_by(*get_sort_key(sort_key)))
    else:
        script_list = (Script.objects.filter(visible=1)
                       .filter(min_weechat__gte=API_STABLE)
                       .order_by(*get_sort_key(sort_key)))
    if filter_name == 'tag':
        script_list = (script_list
                       .filter(tags__regex=r'(^|,)%s($|,)' % filter_value))
    elif filter_name == 'language':
        if filter_value == 'python2-only':
            script_list = (script_list
                           .filter(language='python')
                           .exclude(tags__regex=r'(^|,)py3k-ok($|,)'))
        elif filter_value == 'python3-compatible':
            script_list = (script_list
                           .filter(language='python')
                           .filter(tags__regex=r'(^|,)py3k-ok($|,)'))
        else:
            script_list = script_list.filter(language=filter_value)
    elif filter_name == 'license':
        script_list = script_list.filter(license=filter_value)
    elif filter_name == 'author':
        script_list = script_list.filter(author=filter_value)
    languages = {}
    licenses = {}
    tags = {}
    for script in script_list:
        languages[script.language] = languages.get(script.language, 0) + 1
        if script.language == 'python':
            language = ('python3-compatible' if script.is_py3k_ok()
                        else 'python2-only')
            languages[language] = languages.get(language, 0) + 1
        licenses[script.license] = licenses.get(script.license, 0) + 1
        if script.tags:
            for tag in script.tagslist():
                tags[tag] = tags.get(tag, 0) + 1
    script_filters_displayed, script_filters_sort = (
        request.COOKIES.get('script_filters', '0_name').split('_'))
    if script_filters_sort == 'popularity':
        sort_function = sort_by_popularity
    else:
        sort_function = sort_by_name
    return render(
        request,
        'scripts/list.html',
        {
            'script_list': script_list,
            'api': api,
            'sort_key': sort_key,
            'filter_name': filter_name,
            'filter_value': filter_value,
            'script_filters_displayed': int(script_filters_displayed),
            'script_filters_sort': script_filters_sort,
            'languages': sorted(languages.items(), key=sort_function),
            'licenses': sorted(licenses.items(), key=sort_function),
            'tags': sorted(tags.items(), key=sort_function),
        },
    )


def script_source(request, api='stable', scriptid='', scriptname=''):
    """Page with source of a script."""
    script = None
    if scriptid:
        script = get_object_or_404(Script, id=scriptid)
        try:
            with open(files_path_join(script.path(),
                                      script.name_with_extension()),
                      'rb') as _file:
                htmlsource = get_highlighted_source(_file.read(),
                                                    script.language)
        except:  # noqa: E722
            raise Http404
    else:
        sname = scriptname
        sext = ''
        pos = sname.rfind('.')
        if pos > 0:
            sext = sname[pos+1:]
            sname = sname[0:pos]
        if api == 'legacy':
            script = get_object_or_404(
                Script,
                name=sname,
                language=get_language_from_extension(sext),
                max_weechat=API_OLD,
            )
        else:
            script = get_object_or_404(
                Script,
                name=sname,
                language=get_language_from_extension(sext),
                min_weechat__gte=API_STABLE,
            )
        try:
            with open(files_path_join(script.path(),
                                      script.name_with_extension()),
                      'rb') as _file:
                htmlsource = get_highlighted_source(_file.read(),
                                                    PYGMENTS_LEXER[sext])
        except:  # noqa: E722
            raise Http404
    return render(
        request,
        'scripts/source.html',
        {
            'script': script,
            'htmlsource': htmlsource,
        },
    )


def form_add(request):
    """Page with form to add a script."""
    if request.method == 'POST':
        form = ScriptFormAdd(request.POST, request.FILES)
        if form.is_valid():
            scriptfile = request.FILES['file']
            min_max = form.cleaned_data['min_max'].split(':')
            if min_max[0] == '-':
                min_max[0] = ''
            if min_max[1] == '-':
                min_max[1] = ''

            # add script in database
            now = datetime.now()
            script = Script(visible=False,
                            popularity=0,
                            name=form.cleaned_data['name'],
                            version=form.cleaned_data['version'],
                            url='',
                            language=form.cleaned_data['language'],
                            license=form.cleaned_data['license'],
                            desc_en=form.cleaned_data['description'],
                            requirements=form.cleaned_data['requirements'],
                            min_weechat=min_max[0],
                            max_weechat=min_max[1],
                            author=form.cleaned_data['author'],
                            mail=form.cleaned_data['mail'],
                            added=now,
                            updated=now)

            # write script in pending directory
            filename = files_path_join('scripts', 'pending1',
                                       script.name_with_extension())
            with open(filename, 'w') as _file:
                _file.write(scriptfile.read().replace('\r\n', '\n'))

            # send e-mail
            try:
                if settings.SCRIPTS_MAILTO:
                    subject = ('WeeChat: new script %s' %
                               script.name_with_extension())
                    body = (''
                            'Script      : %s\n'
                            'Version     : %s\n'
                            'Language    : %s\n'
                            'License     : %s\n'
                            'Description : %s\n'
                            'Requirements: %s\n'
                            'Min WeeChat : %s\n'
                            'Max WeeChat : %s\n'
                            'Author      : %s <%s>\n'
                            '\n'
                            'Comment:\n%s\n' %
                            (form.cleaned_data['name'],
                             form.cleaned_data['version'],
                             form.cleaned_data['language'],
                             form.cleaned_data['license'],
                             form.cleaned_data['description'],
                             form.cleaned_data['requirements'],
                             min_max[0],
                             min_max[1],
                             form.cleaned_data['author'],
                             form.cleaned_data['mail'],
                             form.cleaned_data['comment']))
                    sender = '%s <%s>' % (form.cleaned_data['author'],
                                          form.cleaned_data['mail'])
                    email = EmailMessage(subject, body, sender,
                                         settings.SCRIPTS_MAILTO)
                    email.attach_file(filename)
                    email.send()
            except Exception as e:  # noqa: E722
                print(e)
                return HttpResponseRedirect('/scripts/adderror/')

            # save script in database
            script.save()

            return HttpResponseRedirect('/scripts/addok/')
    else:
        form = ScriptFormAdd()
    return render(
        request,
        'scripts/add.html',
        {
            'form': form,
        },
    )


def form_update(request):
    """Page with form to update a script."""
    if request.method == 'POST':
        form = ScriptFormUpdate(request.POST, request.FILES)
        if form.is_valid():
            scriptfile = request.FILES['file']
            script = Script.objects.get(id=form.cleaned_data['script'])

            # send e-mail
            try:
                subject = ('WeeChat: new release for script %s' %
                           script.name_with_extension())
                body = (''
                        'Script     : %s (%s)\n'
                        'New version: %s\n'
                        'Author     : %s <%s>\n'
                        '\n'
                        'Comment:\n%s\n' %
                        (script.name_with_extension(),
                         script.version_weechat(),
                         form.cleaned_data['version'],
                         form.cleaned_data['author'],
                         form.cleaned_data['mail'],
                         form.cleaned_data['comment']))
                sender = '%s <%s>' % (form.cleaned_data['author'],
                                      form.cleaned_data['mail'])
                email = EmailMessage(subject, body, sender,
                                     settings.SCRIPTS_MAILTO)
                email.attach(script.name_with_extension(),
                             scriptfile.read().replace('\r\n', '\n'),
                             'text/plain')
                email.send()
            except:  # noqa: E722
                return HttpResponseRedirect('/scripts/updateerror/')

            return HttpResponseRedirect('/scripts/updateok/')
    else:
        form = ScriptFormUpdate()
    return render(
        request,
        'scripts/update.html',
        {
            'form': form,
        },
    )


def pending(request):
    """Page with scripts pending for approval."""
    script_list = (Script.objects.filter(visible=0)
                   .filter(min_weechat__gte=API_STABLE).order_by('-added'))
    return render(
        request,
        'scripts/pending.html',
        {
            'script_list': script_list,
        },
    )


def python3(request):
    """Page with Python 3 transition."""
    v037_date = Release.objects.get(version='0.3.7').date
    v037_date = datetime(
        year=v037_date.year,
        month=v037_date.month,
        day=v037_date.day,
    )
    status_list = []
    # status when the transition started
    status_list.append({
        'date': datetime(2018, 6, 3),
        'scripts': 347,
        'python_scripts': 216,
        'scripts_ok': 43,
        'scripts_remaining': 173,
    })
    # status today
    scripts = (Script.objects.filter(visible=1)
               .filter(min_weechat__gte=API_STABLE)
               .count())
    python_scripts = (Script.objects.filter(visible=1)
                      .filter(min_weechat__gte=API_STABLE)
                      .filter(language='python')
                      .count())
    scripts_ok = (Script.objects.filter(visible=1)
                  .filter(min_weechat__gte=API_STABLE)
                  .filter(language='python')
                  .filter(tags__regex=r'(^|,)py3k-ok($|,)')
                  .count())
    scripts_remaining = python_scripts - scripts_ok
    status_list.append({
        'date': datetime.now(),
        'today': True,
        'scripts': scripts,
        'python_scripts': python_scripts,
        'scripts_ok': scripts_ok,
        'scripts_remaining': scripts_remaining,
    })
    # status at the end of transition (estimates)
    status_list.append({
        'date': datetime(2019, 12, 31),
        'scripts': 395,
        'python_scripts': 246,
        'scripts_ok': 246,
        'scripts_remaining': 0,
    })
    # compute percentages and flag "future"
    now = datetime.now()
    for status in status_list:
        status['python_scripts_percent'] = (
            (status['python_scripts'] * 100) // status['scripts']
        )
        status['scripts_ok_percent'] = (
            (status['scripts_ok'] * 100) // status['python_scripts']
        )
        status['scripts_remaining_percent'] = (
            100 - status['scripts_ok_percent']
        )
        status['future'] = status['date'] > now
    return render(
        request,
        'scripts/python3.html',
        {
            'python3_date': datetime(2008, 12, 3),
            'v037_date': v037_date,
            'roadmap_start': datetime(2018, 6, 3),
            'roadmap_email': datetime(2018, 6, 16),
            'roadmap_new_py3k': datetime(2018, 7, 1),
            'roadmap_all_py3k': datetime(2018, 9, 1),
            'roadmap_weechat_py3k': datetime(2019, 7, 1),
            'roadmap_end': datetime(2020, 1, 1),
            'status_list': status_list,
        },
    )
