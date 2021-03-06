import logging
import webapp2
from google.appengine.ext.webapp import util
from google.appengine.ext import db
import json as simplejson
from activities import create_subscribe_activity
from model import get_current_youtify_user_model
from model import get_playlist_struct_from_playlist_model
from model import get_playlist_structs_by_id
from model import get_youtify_user_struct
from model import Playlist
from mail import send_new_subscriber_email

class PlaylistFollowersHandler(webapp2.RequestHandler):

    def get(self, playlist_id):
        """Gets the list of users that follow a playlist"""
        playlist_model = Playlist.get_by_id(int(playlist_id))
        json = []

        for key in playlist_model.followers:
            youtify_user_model = db.get(key)
            json.append(get_youtify_user_struct(youtify_user_model))

        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(simplejson.dumps(json))

    def post(self, playlist_id):
        """Follows a playlist"""
        youtify_user_model = get_current_youtify_user_model()
        if youtify_user_model == None:
            self.error(403)
            return

        playlist_model = Playlist.get_by_id(int(playlist_id))
        if playlist_model is None:
            self.error(404)
            return

        if playlist_model.owner.key().id() == youtify_user_model.key().id():
            self.error(400)
            self.response.out.write('You can not subscribe to your own playlists')
            return

        if playlist_model.key() in youtify_user_model.playlist_subscriptions:
            self.error(400)
            self.response.out.write('You already subscribe to this playlist')
            return

        youtify_user_model.playlist_subscriptions.append(playlist_model.key())
        youtify_user_model.save()

        playlist_model.followers.append(youtify_user_model.key())
        playlist_model.nr_of_followers = len(playlist_model.followers)
        playlist_model.save()

        create_subscribe_activity(youtify_user_model, playlist_model)
        send_new_subscriber_email(youtify_user_model, playlist_model)

        self.response.headers['Content-Type'] = 'text/plain'
        self.response.out.write('ok')

    def delete(self, playlist_id):
        """Unfollows a playlist"""
        youtify_user_model = get_current_youtify_user_model()
        if youtify_user_model == None:
            self.error(403)
            return

        playlist_model = Playlist.get_by_id(int(playlist_id))

        youtify_user_model.playlist_subscriptions.remove(playlist_model.key())
        youtify_user_model.save()

        playlist_model.followers.remove(youtify_user_model.key())
        playlist_model.nr_of_followers = len(playlist_model.followers)
        playlist_model.save()

        self.response.headers['Content-Type'] = 'text/plain'
        self.response.out.write('ok')

class SpecificPlaylistHandler(webapp2.RequestHandler):

    def get(self):
        """Get playlist"""
        playlist_id = self.request.path.split('/')[-1]
        playlist_model = Playlist.get_by_id(int(playlist_id))
        playlist_struct = get_playlist_struct_from_playlist_model(playlist_model)

        if playlist_model.private and playlist_model.owner.key() != get_current_youtify_user_model().key():
            self.error(403)
            return

        if playlist_struct:
            self.response.headers['Content-Type'] = 'application/json'
            self.response.headers['Access-Control-Allow-Origin'] = '*'

            self.response.out.write(simplejson.dumps(playlist_struct))
        else:
            self.error(404)

    def post(self):
        """Update playlist"""
        youtify_user_model = get_current_youtify_user_model()
        if youtify_user_model == None:
            self.error(403)
            return

        playlist_id = self.request.path.split('/')[-1]
        playlist_model = Playlist.get_by_id(int(playlist_id))
        json = self.request.get('json', None)
        device = self.request.get('device')

        if json is None:
            self.error(400)
            return

        if playlist_model.owner.key() == youtify_user_model.key():
            if youtify_user_model.device != device:
                self.error(409)
                self.response.out.write('wrong_device')
                return
            else:
                old_playlist = simplejson.loads(json)
                if old_playlist.get('isLoaded', False) is False:
                    self.error(412)
                    self.response.out.write('cannot save a playlist that isn\'t loaded')
                    return

                playlist_model.private = old_playlist.get('isPrivate', False)
                playlist_model.tracks_json = simplejson.dumps(old_playlist['videos'])
                playlist_model.owner = youtify_user_model
                playlist_model.title = old_playlist['title']
                playlist_model.remote_id = old_playlist['remoteId']
                playlist_model.json = None
                playlist_model.save()

                self.response.out.write(str(playlist_model.key().id()))
        else:
            self.error(403)

    def delete(self):
        """Delete playlist"""
        youtify_user_model = get_current_youtify_user_model()
        if youtify_user_model == None:
            self.error(403)
            return

        playlist_id = self.request.path.split('/')[-1]
        playlist_model = Playlist.get_by_id(int(playlist_id))

        if playlist_model.owner.key() == youtify_user_model.key():
            youtify_user_model.playlists.remove(playlist_model.key())
            youtify_user_model.save()

            playlist_model.delete()
        else:
            self.error(403)

class PlaylistsHandler(webapp2.RequestHandler):

    def post(self):
        """Create new playlist"""
        youtify_user_model = get_current_youtify_user_model()
        if youtify_user_model == None:
            self.error(403)
            return

        json_playlist = simplejson.loads(self.request.get('json'))

        if json_playlist is None:
            self.error(500)

        playlist_model = Playlist(owner=youtify_user_model, json=None)
        playlist_model.private = json_playlist.get('isPrivate', False)
        playlist_model.tracks_json = simplejson.dumps(json_playlist['videos'])
        playlist_model.title = json_playlist['title']
        playlist_model.put()

        youtify_user_model.playlists.append(playlist_model.key())
        youtify_user_model.save()

        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(simplejson.dumps(get_playlist_struct_from_playlist_model(playlist_model)))

app = webapp2.WSGIApplication([
        ('/api/playlists/(.*)/followers', PlaylistFollowersHandler),
        ('/api/playlists/.*', SpecificPlaylistHandler),
        ('/api/playlists', PlaylistsHandler),
    ], debug=False)
