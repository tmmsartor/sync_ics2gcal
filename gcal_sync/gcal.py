from apiclient import discovery
import httplib2
import logging
from oauth2client import service_account
from pytz import utc
import sys


class GoogleCalendarService():
    @staticmethod
    def from_srv_acc_file(service_account_file):
        scopes = 'https://www.googleapis.com/auth/calendar'
        credentials = service_account.ServiceAccountCredentials.from_json_keyfile_name(
            service_account_file, scopes=scopes)
        http = credentials.authorize(httplib2.Http())
        service = discovery.build('calendar', 'v3', http=http)
        return service


class GoogleCalendar():
    logger = logging.getLogger('GoogleCalendar')

    def __init__(self, service, calendarId):
        self.service = service
        self.calendarId = calendarId

    def list_events_from(self, start):
        ''' Получение списка событий из GCAL начиная с даты start
        '''
        events = []
        page_token = None
        timeMin = utc.normalize(start.astimezone(utc)).replace(
            tzinfo=None).isoformat() + 'Z'
        while True:
            response = self.service.events().list(calendarId=self.calendarId, pageToken=page_token,
                                                  singleEvents=True, timeMin=timeMin, fields='id,iCalUID,updated').execute()
            if 'items' in response:
                events.extend(response['items'])
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
        self.logger.info('%d events listed', len(events))
        return events

    def find_exists(self, events):
        """ Поиск уже существующих в GCAL событий, из списка событий к вставке

        Arguments:
            events {list} -- list of events

        Returns:
            tuple -- (events_exist, events_not_found)
                  events_exist - list of tuples: (new_event, exists_event)
        """

        events_by_req = []
        exists = []
        not_found = []

        def list_callback(request_id, response, exception):
            found = False
            event = events_by_req[int(request_id)]
            if exception is None:
                found = ([] != response['items'])
            else:
                self.logger.error('exception %s, while listing event with UID: %s', str(
                    exception), event['iCalUID'])
            if found:
                exists.append(
                    (event, response['items'][0]))
            else:
                not_found.append(events_by_req[int(request_id)])

        batch = self.service.new_batch_http_request(callback=list_callback)
        i = 0
        for event in events:
            events_by_req.append(event)
            batch.add(self.service.events().list(calendarId=self.calendarId,
                                                 iCalUID=event['iCalUID'], showDeleted=True, fields='id,iCalUID,updated'), request_id=str(i))
            i += 1
        batch.execute()
        self.logger.info('%d events exists, %d not found',
                         len(exists), len(not_found))
        return exists, not_found

    def insert_events(self, events):
        """ Вставка событий в GCAL

        Arguments:
            events  -- список событий
        """

        events_by_req = []

        def insert_callback(request_id, response, exception):
            if exception is not None:
                event = events_by_req[int(request_id)]
                self.logger.error('failed to insert event with UID: %s, exception: %s', event.get(
                    'UID'), str(exception))
            else:
                event = response
                self.logger.info('event created, id: %s', event.get('id'))

        batch = self.service.new_batch_http_request(callback=insert_callback)
        i = 0
        for event in events:
            events_by_req.append(event)
            batch.add(self.service.events().insert(
                calendarId=self.calendarId, body=event, fields='id,iCalUID,updated'), request_id=str(i))
            i += 1
        batch.execute()

    def patch_events(self, event_tuples):
        """ Обновление (патч) событий в GCAL

        Arguments:
            calendarId  -- ИД календаря
            event_tuples  -- список кортежей событий (новое, старое)
        """

        events_by_req = []

        def patch_callback(request_id, response, exception):
            if exception is not None:
                event = events_by_req[int(request_id)]
                self.logger.error('failed to patch event with UID: %s, exception: %s', event.get(
                    'UID'), str(exception))
            else:
                event = response
                self.logger.info('event patched, id: %s', event.get('id'))

        batch = self.service.new_batch_http_request(callback=patch_callback)
        i = 0
        for event_new, event_old in event_tuples:
            if 'id' not in event_old:
                continue
            events_by_req.append(event_new)
            batch.add(self.service.events().patch(
                calendarId=self.calendarId, eventId=event_old['id'], body=event_new), fields='id,iCalUID,updated', request_id=str(i))
            i += 1
        batch.execute()

    def update_events(self, event_tuples):
        """ Обновление событий в GCAL

        Arguments:
            event_tuples  -- список кортежей событий (новое, старое)
        """

        events_by_req = []

        def update_callback(request_id, response, exception):
            if exception is not None:
                event = events_by_req[int(request_id)]
                self.logger.error('failed to update event with UID: %s, exception: %s', event.get(
                    'UID'), str(exception))
            else:
                event = response
                self.logger.info('event updated, id: %s', event.get('id'))

        batch = self.service.new_batch_http_request(callback=update_callback)
        i = 0
        for event_new, event_old in event_tuples:
            if 'id' not in event_old:
                continue
            events_by_req.append(event_new)
            batch.add(self.service.events().update(
                calendarId=self.calendarId, eventId=event_old['id'], body=event_new, fields='id,iCalUID,updated'), request_id=str(i))
            i += 1
        batch.execute()

    def delete_events(self, events):
        """ Удаление событий в GCAL

        Arguments:
            events  -- список событий
        """

        events_by_req = []

        def delete_callback(request_id, _, exception):
            event = events_by_req[int(request_id)]
            if exception is not None:
                self.logger.error('failed to delete event with UID: %s, exception: %s', event.get(
                    'UID'), str(exception))
            else:
                self.logger.info('event deleted, id: %s', event.get('id'))

        batch = self.service.new_batch_http_request(callback=delete_callback)
        i = 0
        for event in events:
            events_by_req.append(event)
            batch.add(self.service.events().delete(
                calendarId=self.calendarId, eventId=event['id']), request_id=str(i))
            i += 1
        batch.execute()

    def make_public(self):
        rule_public = {
            'scope': {
                'type': 'default',
            },
            'role': 'reader'
        }
        return self.service.acl().insert(calendarId=self.calendarId, body=rule_public).execute()

    def add_owner(self, email):
        rule_owner = {
            'scope': {
                'type': 'user',
                'value': email,
            },
            'role': 'owner'
        }
        return self.service.acl().insert(calendarId=self.calendarId, body=rule_owner).execute()