#!/usr/bin/env python2
import urllib
import urllib2
import HTMLParser
import cookielib
import bingFlyoutParser as bfp
import helpers
from bingSearchStringsGenerator import parseBingNews, BING_NEWS_URL

FACEBOOK_EMAIL = "xxx"
FACEBOOK_PASSWORD = "xxx"
BING_URL = 'http://www.bing.com'

# extend urllib.addinfourl like it defines @contextmanager (to use with "with" keyword)
urllib.addinfourl.__enter__ = lambda self: self
urllib.addinfourl.__exit__  = lambda self, type, value, traceback: self.close()

class AuthenticationError(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)

class HTTPRefererHandler(urllib2.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        if not "Referer" in req.headers:
#             if req.get_host() == "www.bing.com":
#                 req.headers["Referer"] = "http://www.bing.com/"
#             else:
                req.headers["Referer"] = req.get_full_url()
        return urllib2.HTTPRedirectHandler.http_error_302(self, req, fp, code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_302

class HTMLFormInputsParser(HTMLParser.HTMLParser):
    def __init__(self):
        HTMLParser.HTMLParser.__init__(self)
        self.inputs = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'input':
            name = value = ''
            for attr in attrs:
                if attr[0] == 'name':
                    name = attr[1]
                elif attr[0] == 'value':
                    value = attr[1]
            if name != '' and value != '':
                self.inputs[name] = value.encode("utf-8")

class BingRewards:
    class RewardResult:
        def __init__(self, reward):
            if reward is None or not isinstance(reward, bfp.Reward):
                raise TypeError("reward is not of Reward type")

            self.o = reward
            self.isError = False
            self.message = ""
# action applied to the reward
            self.action  = bfp.Reward.Type.Action.WARN

    BING_REQUEST_PERMISSIONS = "http://www.bing.com/fd/auth/signin?action=interactive&provider=facebook&return_url=http%3a%2f%2fwww.bing.com%2f&src=EXPLICIT&perms=read_stream%2cuser_photos%2cfriends_photos&sig="
    BING_FLYOUT_PAGE = "http://www.bing.com/rewardsapp/flyoutpage?style=v2"
# common headers for all requests
    HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-us,en;q=0.5",
        "Accept-Charset": "utf-8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    def __init__(self, facebook_email, facebook_password):
        self.facebook_email = facebook_email
        self.facebook_password = facebook_password
# bingMainUrl will be set in the end of self.authenticate() method
        self.bingMainUrl = None
        cookies = cookielib.CookieJar()
        self.opener = urllib2.build_opener(#urllib2.HTTPSHandler(debuglevel = 1),     # be verbose on HTTPS
                                           #urllib2.HTTPHandler(debuglevel = 1),      # be verbose on HTTP
                                           HTTPRefererHandler,                       # add Referer header on redirect
                                           urllib2.HTTPCookieProcessor(cookies))     # keep cookies

    def authenticate(self):
        """
        Authenticates a user on bing.com with his/her Facebook account.
        FACEBOOK_EMAIL and FACEBOOK_PASSWORD for this class must be set to appropriate values.

        throws AuthenticationError if authentication can not be passed
        throws HTMLParser.HTMLParseError
        throws urllib2.HTTPError if the server couldn't fulfill the request
        throws urllib2.URLError if failed to reach the server
        """
#        print "Requesting bing.com"

# request http://www.bing.com
        request = urllib2.Request(url = BING_URL, headers = self.HEADERS)
        with self.opener.open(request) as response:
            page = helpers.getResponseBody(response)

# get connection URL for provider Facebook
        s = page.index('"Facebook":"')
        s += len('"Facebook":"')
        e = page.index('"', s)
        url = page[s:e]
        s = url.index('sig=')
        s += len('sig=')
        e = url.find('&', s)
        if e == -1:
            e = len(url)
        url = self.BING_REQUEST_PERMISSIONS + url[s:e]

#        print "Now requesting facebook authentication page"

# request FACEBOOK_CONNECT_ORIGINAL_URL
        request = urllib2.Request(url = url, headers = self.HEADERS)
        request.add_header("Referer", BING_URL)
        with self.opener.open(request) as response:
            referer = response.geturl()
# get Facebook authenctication form action url
            page = helpers.getResponseBody(response)

        s = page.index('<form id="login_form"')
        s = page.index('action="', s)
        s += len('action="')
        e = page.index('"', s)
        url = page[s:e]

# find all html elements which need to be sent to the server
        s = page.index('>', s)
        s += 1
        e = page.index('</form>')

        parser = HTMLFormInputsParser()
        parser.feed(page[s:e].decode("utf-8"))
        parser.close()
        parser.inputs["email"] = self.facebook_email
        parser.inputs["pass"] = self.facebook_password

#        print "Now passing facebook authentication"

# pass facebook authentication
        postFields = urllib.urlencode(parser.inputs)
        request = urllib2.Request(url, postFields, self.HEADERS)
        request.add_header("Referer", referer)
        with self.opener.open(request) as response:
            url = response.geturl()
# if that's not BING_URL => authentication wasn't pass => write the page to the file and report
            if url.find(BING_URL) == -1:
                del self.bingMainUrl
                self.bingMainUrl = None
                try:
                    filename = helpers.dumpErrorPage(common.getResponseBody(response))
                    s = "check " + filename + " file for more information"
                except IOError:
                    s = "no further information could be provided - failed to write a file into " + \
                        helpers.RESULTS_DIR + " subfolder"
                raise AuthenticationError("Authentication could not be passed:\n" + s)
            self.bingMainUrl = url

    def requestFlyoutPage(self):
        """
        Returns bing.com flyout page
        This page shows what rewarding activity can be performed in
        order to earn Bing points
        throws AuthenticationError if self.bingMainUrl is not set
        """
        if self.bingMainUrl is None:
            raise AuthenticationError("bingMainUrl is not set, probably you haven't passed the authentication")

        url = self.BING_FLYOUT_PAGE
        request = urllib2.Request(url = url, headers = self.HEADERS)
        request.add_header("Referer", BING_URL)
        with self.opener.open(request) as response:
            page = helpers.getResponseBody(response)
        return page

    def getRewardsPoints(self):
        """
        Returns rewards points as int
        throws AuthenticationError if self.bingMainUrl is not set
        """

        if self.bingMainUrl is None:
            raise AuthenticationError("bingMainUrl is not set, probably you haven't passed the authentication")

# report activity
        postFields = urllib.urlencode( { "url" : self.bingMainUrl, "V" : "web" } )
        url = "http://www.bing.com/rewardsapp/reportActivity"
        request = urllib2.Request(url, postFields, self.HEADERS)
        request.add_header("Referer", BING_URL)
        with self.opener.open(request) as response:
            page = helpers.getResponseBody(response)

# parse activity page
        s = page.index("txt.innerHTML = '")
        s += len("txt.innerHTML = '")
        e = page.index("'", s)
        return int(page[s:e])

    def __processHit(self, reward):
        """Processes bfp.Reward.Type.Action.HIT and returns self.RewardResult"""
        res = self.RewardResult(reward)
        pointsEarned = self.getRewardsPoints()
        request = urllib2.Request(url = reward.url, headers = self.HEADERS)
        with self.opener.open(request) as response:
            page = helpers.getResponseBody(response)
        pointsEarned = self.getRewardsPoints() - pointsEarned
# if HIT is against bfp.Reward.Type.RE_EARN_CREDITS - check if pointsEarned is the same to
# pointsExpected
        indCol = bfp.Reward.Type.Col.INDEX
        if reward.tp[indCol] == bfp.Reward.Type.RE_EARN_CREDITS[indCol]:
            matches = bfp.Reward.Type.RE_EARN_CREDITS[bfp.Reward.Type.Col.NAME].search(reward.name)
            pointsExpected = int(matches.group(1))
            if pointsExpected != pointsEarned:
                filename = helpers.dumpErrorPage(page)
                res.isError = True
                res.message = "Expected to earn " + pointsExpected + " points, but earned " + \
                              pointsEarned + " points. Check " + filename + " for further information"
        return res

    def __processSearch(self, reward):
        """Processes bfp.Reward.Type.Action.SEARCH and returns self.RewardResult"""
        res = self.RewardResult(reward)

        indCol = bfp.Reward.Type.Col.INDEX
        if reward.tp[indCol] != bfp.Reward.Type.SEARCH_AND_EARN[indCol]:
            res.isError = True
            res.message = "Don't know how to process this search"
            return res

# find out how many searches need to be performed
        matches = bfp.Reward.Type.SEARCH_AND_EARN_DESCR_RE.search(reward.description)
        rewardsCount    = int(matches.group(1))
        rewardCost      = int(matches.group(2))
        maxRewardsCount = int(matches.group(4))
        searchesCount = maxRewardsCount * rewardCost / rewardsCount

        if reward.url == "":
            res.isError = True
            res.message = "Epected url part in \"" + reward.name + "\" reward, but url was empty"
            return res

        request = urllib2.Request(url = BING_NEWS_URL, headers = self.HEADERS)
        with self.opener.open(request) as response:
            page = helpers.getResponseBody(response)
        strings = parseBingNews(page, searchesCount)

        return res

    def process(self, rewards):
        """
        Runs an action for each of rewards as described in self.RewardType
        returns results list of self.RewardResult objects
        """
        if rewards is None or not isinstance(rewards, list):
            raise TypeError("rewards is not an instance of list")

        results = []

        for r in rewards:
            if r.tp is None:
                action = bfp.Reward.Type.Action.WARN
            else:
                action = r.tp[bfp.Reward.Type.Col.ACTION]

            if action == bfp.Reward.Type.Action.HIT:
                res = self.__processHit(r)
            elif action == bfp.Reward.Type.Action.SEARCH:
                res = self.__processSearch(r)
            else:
                res = self.RewardResult(r)

            res.action = action
            results.append(res)

        return results

    def __printReward(self, reward):
        """Prints a reward"""
        print "name        : %s" % reward.name
        if reward.url != "":
            print "url         : %s" % reward.url
        if reward.progressMax != 0:
            print "progressCur : %d" % reward.progressCurrent
            print "progressMax : %d" % reward.progressMax
            print "progress %%  : %0.2f%%" % reward.progressPercentage()
        if reward.isDone:
            print "is done     : true"
        print "description : %s" % reward.description

    def printRewards(self, rewards):
        """
        Prints out rewards list
        throws TypeError if rewards is None or not instance of list
        """
        if rewards is None or not isinstance(rewards, list):
            raise TypeError("rewards is not an instance of list")

        i = 0
        total = len(rewards)
        for r in rewards:
            i += 1
            print "Reward %d/%d:" % (i, total)
            print "-----------"
            self.__printReward(r)
            print

    def __printResult(self, result):
        """Prints a result"""
        self.__printReward(result.o)
        if result.isError:
            print "   Error    :   true"
        print "   Message  : " + result.message
        print "   Action   : " + bfp.Reward.Type.Action.toStr(result.action)


    def printResults(self, results):
        """
        Prints out results list
        throws TypeError if results is None or not instance of list
        """
        if results is None or not isinstance(results, list):
            raise TypeError("results is not an instance of list")

        i = 0
        total = len(results)
        for r in results:
            i += 1
            print "Result %d/%d:" % (i, total)
            print "-----------"
            self.__printResult(r)
            print

if __name__ == "__main__":
    try:
        helpers.createResultsDir(__file__)

        bingRewards = BingRewards(FACEBOOK_EMAIL, FACEBOOK_PASSWORD)
        bingRewards.authenticate()
        points  = bingRewards.getRewardsPoints()
        rewards = bfp.parseFlyoutPage(bingRewards.requestFlyoutPage(), BING_URL)

        bingRewards.printRewards(rewards)
        results = bingRewards.process(rewards)

        bingRewards.printResults(results)
        print
        print "Points before: %d" % points
        print "Points after:  %d" % bingRewards.getRewardsPoints()

    except AuthenticationError, e:
        print "AuthenticationError:\n%s" % e

    except HTMLParser.HTMLParseError, e:
        print "HTMLParserError: %s" % e

    except urllib2.HTTPError, e:
        print "The server couldn't fulfill the request."
        print "Error code: ", e.code

    except urllib2.URLError, e:
        print "Failed to reach the server."
        print "Reason: ", e.reason
