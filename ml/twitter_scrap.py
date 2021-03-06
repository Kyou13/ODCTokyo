# coding: utf-8

# -*- coding: utf-8 -*-
 
from requests_oauthlib import OAuth1Session
import json
import datetime, time, sys
from abc import ABCMeta, abstractmethod
import re
from gensim.models import word2vec
import MeCab
import os
import sys

CK = os.environ['CK']                             # Consumer Key
CS = os.environ['CS']    # Consumer Secret
AT = os.environ['AT']    # Access Token
AS = os.environ['AS']         # Accesss Token Secert

def trim_doc(lines):
    sep_doc = []

    for s in range(len(lines)):
        # 空白行は削除
        if lines[s] == '\n':
            sep_docs[tag] = ''.join(sep_doc)
            sep_doc = []

        # ツイート文章
        else :
            # URLを除去
            lines[s] = re.sub('https?://[\w/:%#\$&\?\(\)~\.=\+\-]+','',lines[s])

        sep_doc.append(lines[s])

    return sep_doc

class TweetsGetter(object):
    __metaclass__ = ABCMeta
 
    def __init__(self):
        self.session = OAuth1Session(CK, CS, AT, AS)
 
    @abstractmethod
    def specifyUrlAndParams(self, keyword):
        '''
        呼出し先 URL、パラメータを返す
        '''
 
    @abstractmethod
    def pickupTweet(self, res_text, includeRetweet):
        '''
        res_text からツイートを取り出し、配列にセットして返却
        '''
 
    @abstractmethod
    def getLimitContext(self, res_text):
        '''
        回数制限の情報を取得 （起動時）
        '''
 
    def collect(self, total = -1, onlyText = False, includeRetweet = False):
        '''
        ツイート取得を開始する
        '''
 
        #----------------
        # 回数制限を確認
        #----------------
        self.checkLimit()
 
        #----------------
        # URL、パラメータ
        #----------------
        url, params = self.specifyUrlAndParams()
        params['include_rts'] = str(includeRetweet).lower()
        # include_rts は statuses/user_timeline のパラメータ。search/tweets には無効
 
        #----------------
        # ツイート取得
        #----------------
        cnt = 0
        unavailableCnt = 0
        while True:
            res = self.session.get(url, params = params)
            if res.status_code == 503:
                # 503 : Service Unavailable
                if unavailableCnt > 10:
                    raise Exception('Twitter API error %d' % res.status_code)
 
                unavailableCnt += 1
                print ('Service Unavailable 503')
                self.waitUntilReset(time.mktime(datetime.datetime.now().timetuple()) + 30)
                continue
 
            unavailableCnt = 0
 
            if res.status_code != 200:
                raise Exception('Twitter API error %d' % res.status_code)
 
            tweets = self.pickupTweet(json.loads(res.text))
            if len(tweets) == 0:
                # len(tweets) != params['count'] としたいが
                # count は最大値らしいので判定に使えない。
                # ⇒  "== 0" にする
                # https://dev.twitter.com/discussions/7513
                break
 
            for tweet in tweets:
                if (('retweeted_status' in tweet) and (includeRetweet is False)):
                    pass
                else:
                    if onlyText is True:
                        yield tweet['text']
                    else:
                        yield tweet
 
                    cnt += 1
                    if cnt % 100 == 0:
                        print ('%d件 ' % cnt)
 
                    if total > 0 and cnt >= total:
                        return
 
            params['max_id'] = tweet['id'] - 1
 
            # ヘッダ確認 （回数制限）
            # X-Rate-Limit-Remaining が入ってないことが稀にあるのでチェック
            if ('X-Rate-Limit-Remaining' in res.headers and 'X-Rate-Limit-Reset' in res.headers):
                if (int(res.headers['X-Rate-Limit-Remaining']) == 0):
                    self.waitUntilReset(int(res.headers['X-Rate-Limit-Reset']))
                    self.checkLimit()
            else:
                print ('not found  -  X-Rate-Limit-Remaining or X-Rate-Limit-Reset')
                self.checkLimit()
 
    def checkLimit(self):
        '''
        回数制限を問合せ、アクセス可能になるまで wait する
        '''
        unavailableCnt = 0
        while True:
            url = "https://api.twitter.com/1.1/application/rate_limit_status.json"
            res = self.session.get(url)
 
            if res.status_code == 503:
                # 503 : Service Unavailable
                if unavailableCnt > 10:
                    raise Exception('Twitter API error %d' % res.status_code)
 
                unavailableCnt += 1
                print ('Service Unavailable 503')
                self.waitUntilReset(time.mktime(datetime.datetime.now().timetuple()) + 30)
                continue
 
            unavailableCnt = 0
 
            if res.status_code != 200:
                raise Exception('Twitter API error %d' % res.status_code)
 
            remaining, reset = self.getLimitContext(json.loads(res.text))
            if (remaining == 0):
                self.waitUntilReset(reset)
            else:
                break
 
    def waitUntilReset(self, reset):
        '''
        reset 時刻まで sleep
        '''
        seconds = reset - time.mktime(datetime.datetime.now().timetuple())
        seconds = max(seconds, 0)
        print ('\n     =====================')
        print ('     == waiting %d sec ==' % seconds)
        print ('     =====================')
        sys.stdout.flush()
        time.sleep(seconds + 10)  # 念のため + 10 秒
 
    @staticmethod
    def bySearch(keyword):
        return TweetsGetterBySearch(keyword)
 
    @staticmethod
    def byUser(screen_name):
        return TweetsGetterByUser(screen_name)
 
 
class TweetsGetterBySearch(TweetsGetter):
    '''
    キーワードでツイートを検索
    '''
    def __init__(self, keyword):
        super(TweetsGetterBySearch, self).__init__()
        self.keyword = keyword
        
    def specifyUrlAndParams(self):
        '''
        呼出し先 URL、パラメータを返す
        '''
        url = 'https://api.twitter.com/1.1/search/tweets.json'
        params = {'q':self.keyword, 'count':100}
        return url, params
 
    def pickupTweet(self, res_text):
        '''
        res_text からツイートを取り出し、配列にセットして返却
        '''
        results = []
        for tweet in res_text['statuses']:
            results.append(tweet)
 
        return results
 
    def getLimitContext(self, res_text):
        '''
        回数制限の情報を取得 （起動時）
        '''
        remaining = res_text['resources']['search']['/search/tweets']['remaining']
        reset     = res_text['resources']['search']['/search/tweets']['reset']
 
        return int(remaining), int(reset)
    
 
class TweetsGetterByUser(TweetsGetter):
    '''
    ユーザーを指定してツイートを取得
    '''
    def __init__(self, screen_name):
        super(TweetsGetterByUser, self).__init__()
        self.screen_name = screen_name
        
    def specifyUrlAndParams(self):
        '''
        呼出し先 URL、パラメータを返す
        '''
        url = 'https://api.twitter.com/1.1/statuses/user_timeline.json'
        params = {'screen_name':self.screen_name, 'count':200}
        return url, params
 
    def pickupTweet(self, res_text):
        '''
        res_text からツイートを取り出し、配列にセットして返却
        '''
        results = []
        for tweet in res_text:
            results.append(tweet)
 
        return results
 
    def getLimitContext(self, res_text):
        '''
        回数制限の情報を取得 （起動時）
        '''
        remaining = res_text['resources']['statuses']['/statuses/user_timeline']['remaining']
        reset     = res_text['resources']['statuses']['/statuses/user_timeline']['reset']
 
        return int(remaining), int(reset)

def count_pos_word(text):

    # ベクトルの閾値
    sep_vec = 0.5

    # model読み込み
    model = word2vec.Word2Vec.load('wiki.model')

    mecab = MeCab.Tagger("-Ochasen")
    lines = mecab.parse(text).splitlines()
    words = []
    count_word = 0
    for line in lines:
        chunks = line.split('\t')
        # 動詞,形容詞,名詞のみを抽出
        if len(chunks) > 3 and (chunks[3].startswith('動詞') or chunks[3].startswith('形容詞') or (chunks[3].startswith('名詞') and not chunks[3].startswith('名詞-数'))):
            try:
                score = model.similarity('楽しい', chunks[0])
            except KeyError:
                # print("not in vocablary")
                continue

            if score > sep_vec:
                count_word = count_word + 1

    return count_word

if __name__ == '__main__':
 
    # キーワードで取得
    keyword = sys.argv[1]
    # keyword = u'TokyoTower'
    getter = TweetsGetter.bySearch(keyword)

    # ユーザーを指定して取得 （screen_name）
    # screen_name = 'IHayato'
    # getter = TweetsGetter.byUser(screen_name)
 
    tweet_cnt = 0
    # f = open('./database/{}.txt'.format(keyword, str), 'w') # 書き込みモードで開く

    total_pos_words =  0

    for tweet in getter.collect(total = 3):
        # print(tweet['text'])
        # 年度を指定
        # if tweet['created_at'][-4:] == year:
        if True:
            tweet_cnt += 1 # 取得tweet数
            # print('------ %d' % tweet_cnt)
            # print('{} {} {}'.format(tweet['id'], tweet['created_at'], '@'+tweet['user']['screen_name']))

            _tweet = tweet['text']

            _tweet = _tweet.split('\n')
            _text = trim_doc(_tweet)

            text = []
            # ツイート内容から空白行除去
            for word in _text:
                if word != '':
                    text.append(word)
            # print(text)
            text = '\n'.join(text)

            total_pos_words = total_pos_words + count_pos_word(text)

            # f.write(tweet['created_at'] + "\n" + text + "\n\n")

    print("おすすめ度：{}".format(total_pos_words/tweet_cnt))
    # f.close() # ファイルを閉じる
