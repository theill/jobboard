#!/usr/bin/env python
#
# Copyright 2010 Commanigy
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""A barebones AppEngine application that uses Facebook for login."""

FACEBOOK_APP_ID = "116481168413579"
FACEBOOK_APP_SECRET = "c5bebc5b58f22fe46a2d0ac08cd6bfbf"

import base64
import cgi
import Cookie
import email.utils
import hashlib
import hmac
import os.path
import time
import urllib
import facebook
import os.path
import wsgiref.handlers
import logging

from django.utils import simplejson as json

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import template

# load all helper templates
from google.appengine.ext.webapp import template
template.register_template_library('helpers.offers_helper')

class Category(db.Model):
  id = db.StringProperty(required=True)
  name = db.StringProperty(required=True)
  description = db.StringProperty
  image_url = db.StringProperty(required=True)

class User(db.Model):
  id = db.StringProperty(required=True)
  created = db.DateTimeProperty(auto_now_add=True)
  updated = db.DateTimeProperty(auto_now=True)
  name = db.StringProperty(required=True)
  profile_url = db.StringProperty(required=True)
  access_token = db.StringProperty(required=True)

class Offer(db.Model):
  created = db.DateTimeProperty(auto_now_add=True)
  updated = db.DateTimeProperty(auto_now=True)
  user_id = db.StringProperty(required=True)
  description = db.StringProperty(required=True)
  skills = db.StringListProperty(required=True)
  salary = db.IntegerProperty(required=True)

class BaseHandler(webapp.RequestHandler):
  """Provides access to the active Facebook user in self.current_user

  The property is lazy-loaded on first access, using the cookie saved
  by the Facebook JavaScript SDK to determine the user ID of the active
  user. See http://developers.facebook.com/docs/authentication/ for
  more information.
  """
  @property
  def current_user(self):
    logging.info("getting current user")
    if not hasattr(self, "_current_user"):
      logging.info("setting user")
      self._current_user = None
      cookie = facebook.get_user_from_cookie(
          self.request.cookies, FACEBOOK_APP_ID, FACEBOOK_APP_SECRET)
      logging.info("cookie loaded is %s" % cookie)
      if cookie:
        # Store a local instance of the user data so we don't need
        # a round-trip to Facebook on every request
        user = User.get_by_key_name(cookie["uid"])
        if not user:
          graph = facebook.GraphAPI(cookie["access_token"])
          profile = graph.get_object("me")
          user = User(key_name=str(profile["id"]),
                      id=str(profile["id"]),
                      name=profile["name"],
                      profile_url=profile["link"],
                      access_token=cookie["access_token"])
          user.put()
        elif user.access_token != cookie["access_token"]:
          user.access_token = cookie["access_token"]
          user.put()
        self._current_user = user
      return self._current_user

  def render(self, path, **kwargs):
    args = dict(current_user=self.current_user,
                facebook_app_id=FACEBOOK_APP_ID)
    args.update(kwargs)
    path = os.path.join(os.path.dirname(__file__), path)
    self.response.out.write(template.render(path, args))


class HomeHandler(BaseHandler):
  def get(self):
    categories = Category.all()
    self.render("index.html", categories=categories)

class OfferWorkHandler(BaseHandler):
  def get(self):
    categories = Category.all()
    self.render("offerwork.html", categories=categories)

class OfferHandler(BaseHandler):
    def get(self):
        self.render("offer.html")

    def post(self):
      """docstring for post"""
      description = self.request.get("description")
      salary = int(self.request.get("salary"))
      skills = self.request.get_all("skills[]")
      offer = Offer(description=description, skills=skills, salary=salary, user_id=self.current_user.id)
      offer.put()
      self.redirect("/")

class ProfileHandler(BaseHandler):
    def get(self, id):
        offer = Offer.get(id)
        self.render("profile.html", offer=offer, page_url=self.request.url)

class OffersHandler(BaseHandler):
    def get(self):
      q = Offer.all()
      # q.filter("last_name =", "Smith")
      # q.filter("height <", 72)
      q.order("-created")
      
      offers = q.fetch(10)
      self.render("offers.html", offers=offers)

class TabHandler(BaseHandler):
  """docstring for TabHandler"""

  def get(self):
    """docstring for get"""
    Category(id="house", name="House", description="", image_url="/img/house.png").put()
    Category(id="garden", name="Garden", description="", image_url="/img/garden.png").put()
    Category(id="dinner", name="Dinner", description="", image_url="/img/dinner.png").put()
    Category(id="tech", name="Tech", description="", image_url="/img/tech.png").put()
    Category(id="education", name="Education", description="", image_url="/img/education.png").put()
    path = os.path.join(os.path.dirname(__file__), "tab.html")
    self.response.out.write(template.render(path, []))

class LoginHandler(BaseHandler):
    def get(self):
        verification_code = self.request.get("code")
        
        args = dict(client_id=FACEBOOK_APP_ID, redirect_uri=self.request.path_url, scope="publish_stream")
        if self.request.get("code"):
            args["client_secret"] = FACEBOOK_APP_SECRET
            args["code"] = self.request.get("code")
            response = cgi.parse_qs(urllib.urlopen(
                "https://graph.facebook.com/oauth/access_token?" +
                urllib.urlencode(args)).read())
            access_token = response["access_token"][-1]

            # Download the user profile and cache a local instance of the
            # basic profile info
            profile = json.load(urllib.urlopen(
                "https://graph.facebook.com/me?" +
                urllib.urlencode(dict(access_token=access_token))))
            user = User(key_name=str(profile["id"]), id=str(profile["id"]),
                        name=profile["name"], access_token=access_token,
                        profile_url=profile["link"])
            user.put()
            set_cookie(self.response, "fb_user", str(profile["id"]),
                       expires=time.time() + 30 * 86400)
            self.redirect("/")
        else:
            self.redirect(
                "https://graph.facebook.com/oauth/authorize?" +
                urllib.urlencode(args))


class LogoutHandler(BaseHandler):
    def get(self):
        set_cookie(self.response, "fb_user", "", expires=time.time() - 86400)
        self.redirect("/")


def set_cookie(response, name, value, domain=None, path="/", expires=None):
    """Generates and signs a cookie for the give name/value"""
    timestamp = str(int(time.time()))
    value = base64.b64encode(value)
    signature = cookie_signature(value, timestamp)
    cookie = Cookie.BaseCookie()
    cookie[name] = "|".join([value, timestamp, signature])
    cookie[name]["path"] = path
    if domain: cookie[name]["domain"] = domain
    if expires:
        cookie[name]["expires"] = email.utils.formatdate(
            expires, localtime=False, usegmt=True)
    response.headers._headers.append(("Set-Cookie", cookie.output()[12:]))


def parse_cookie(value):
    """Parses and verifies a cookie value from set_cookie"""
    if not value: return None
    parts = value.split("|")
    if len(parts) != 3: return None
    if cookie_signature(parts[0], parts[1]) != parts[2]:
        logging.warning("Invalid cookie signature %r", value)
        return None
    timestamp = int(parts[1])
    if timestamp < time.time() - 30 * 86400:
        logging.warning("Expired cookie %r", value)
        return None
    try:
        return base64.b64decode(parts[0]).strip()
    except:
        return None


def cookie_signature(*parts):
    """Generates a cookie signature.

    We use the Facebook app secret since it is different for every app (so
    people using this example don't accidentally all use the same secret).
    """
    hash = hmac.new(FACEBOOK_APP_SECRET, digestmod=hashlib.sha1)
    for part in parts: hash.update(part)
    return hash.hexdigest()



def main():
    util.run_wsgi_app(webapp.WSGIApplication([
      (r"/", HomeHandler),
      (r"/tab", TabHandler),
      (r"/offerwork", OfferWorkHandler),
      (r"/offer/(.*)", ProfileHandler),
      (r"/offer", OfferHandler),
      (r"/offers", OffersHandler),
      (r"/auth/login", LoginHandler),
      (r"/auth/logout", LogoutHandler),
      ]))


if __name__ == "__main__":
  main()
