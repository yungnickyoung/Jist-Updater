from flask import Flask, request, jsonify, abort, Response
from threading import Thread
from bcolors import bcolors
import requests
import sys
import datetime
import time

app = Flask(__name__)
datetime_f = '%a, %d %b %Y %H:%M:%S %Z'

## /ready -- POST
# Initiates update checking on all existing articles in database
#
# Returns: 
#   - 202: Update process has successfully been initiated
#   - 500: If error occurs while attempting to initiate update process
@app.route("/ready", methods = ['POST'])
def serviceReady():
    try:
        thr = Thread(target=updateArticles, args=[])
        print(bcolors.GREEN + "Update process initiated." + bcolors.ENDC, file=sys.stderr)
        thr.start()
    except Exception as e:
        print(bcolors.FAIL + "ERROR while attempting to initiate update process: " + str(e) + bcolors.ENDC, file=sys.stderr)
        abort(Response(status=500, response="500: Error (500): Unable to start update process: " + str(e)))

    return '', 202

def updateArticles():
    startTime = time.time()

    # Retrieve all articles from db
    resp = requests.get(url='http://jist-database-api:5003/articles')
    if resp.status_code != 200:
        print(bcolors.FAIL + "ERROR: {0} RESPONSE FROM DATABASE API: {1}".format(resp.status_code, resp.text), file=sys.stderr)
        return

    articles = resp.json()

    articlesChangedCodeCount = {}
    articlesUnchangedCodeCount = {}

    for article in articles:
        # Get time since last update for this article
        lastModifiedTime = datetime.datetime.strptime(article['last_modified'], datetime_f)
        currentTime = datetime.datetime.utcnow()
        elapsedTime = currentTime - lastModifiedTime

        # Don't update articles that were checked in the last 15 minutes
        if (elapsedTime.seconds < 600 and elapsedTime.days == 0) or elapsedTime.days > 0:
            continue

        data = {
            'domain': article['domain'],
            'article_url': article['article_url'],
            'amp_url': article['amp_url']
        }

        # Get article contents and hash
        resp = requests.post(url='http://jist-html-parser:5001/parse', json=data)
        if resp.status_code != 200:
            print(bcolors.FAIL + "ERROR: {0} RESPONSE FROM HTML PARSER: {1}\nSkipping update check for article...".format(resp.status_code, resp.text), file=sys.stderr)
            continue

        newArticleText = resp.json()['article_text']
        newArticleHash = resp.json()['article_hash']
        
        # Check if calculated hash matches stored hash
        if newArticleHash == article['article_hash']: # Hash is the same -> No change in information. Still need to UPDATE to update the last_modified timestamp
            data = {
                'summary_s': article['summary_s'],
                'summary_m': article['summary_m'],
                'summary_l': article['summary_l'],
                'article_hash': article['article_hash']
            }

            # Update database
            resp = requests.put(url='http://jist-database-api:5003/articles', json=data, params={ "id": article['id'] })

            if resp.status_code == 200:
                print(bcolors.GREEN + "(Unchanged) Database response 201 (Success) - ID: {}".format(article['id']) + bcolors.ENDC, file=sys.stderr)
            elif resp.status_code == 400:
                print(bcolors.WARNING + "(Unchanged) Database response 400 (Missing data?) - ID: {}".format(article['id']) + bcolors.ENDC, file=sys.stderr)
            elif resp.status_code == 500:
                print(bcolors.FAIL + "(Unchanged) Database response 500 (Error occurred during UPDATE) - ID: {}".format(article['id']) + bcolors.ENDC, file=sys.stderr)
            else:
                print(bcolors.FAIL + "(Unchanged) Database response {0} (UNUSUAL) - ID: {1}".format(resp.status_code, article['id']) + bcolors.ENDC, file=sys.stderr)

            try:
                articlesUnchangedCodeCount[resp.status_code] += 1
            except:
                articlesUnchangedCodeCount[resp.status_code] = 1


        else: # Hashes are different -> Need to update the database with the new hash and summary
            resp = requests.post(url='http://jist-summarizer:5002/summarize', json={ 'article_text': newArticleText })
            if resp.status_code != 200:
                print(bcolors.FAIL + "ERROR: {0} RESPONSE FROM SUMMARIZER: {1}\nSkipping update check for article...".format(resp.status_code, resp.text), file=sys.stderr)
                continue

            newArticleSummary = resp.json()['summary']

            data = {
                'summary_s': newArticleSummary,
                'summary_m': newArticleSummary,
                'summary_l': newArticleSummary,
                'article_hash': newArticleHash,
            }

            # Update database
            resp = requests.put(url='http://jist-database-api:5003/articles', json=data, params={ "id": article['id'] })

            if resp.status_code == 200:
                print(bcolors.BLUE + "(Changed) Database response 201 (Success) - ID: {}".format(article['id']) + bcolors.ENDC, file=sys.stderr)
            elif resp.status_code == 400:
                print(bcolors.WARNING + "(Changed) Database response 400 (Missing data?) - ID: {}".format(article['id']) + bcolors.ENDC, file=sys.stderr)
            elif resp.status_code == 500:
                print(bcolors.FAIL + "(Changed) Database response 500 (Error occurred during UPDATE) - ID: {}".format(article['id']) + bcolors.ENDC, file=sys.stderr)
            else:
                print(bcolors.FAIL + "(Changed) Database response {0} (UNUSUAL) - ID: {1}".format(resp.status_code, article['id']) + bcolors.ENDC, file=sys.stderr)

            try:
                articlesChangedCodeCount[resp.status_code] += 1
            except:
                articlesChangedCodeCount[resp.status_code] = 1

    print(bcolors.GREEN + "Database responses (unchanged articles): {}".format(str(articlesUnchangedCodeCount)) + bcolors.ENDC, file=sys.stderr)
    print(bcolors.GREEN + "Database responses (changed articles): {}".format(str(articlesChangedCodeCount)) + bcolors.ENDC, file=sys.stderr)

    endTime = time.time()
    print("\n" + bcolors.BLUE + "Elapsed time: " + str(int((endTime - startTime) / 60)) + " min " + str(int((endTime - startTime) % 60)) + " sec" + bcolors.ENDC, file=sys.stderr)
    sys.stderr.flush()

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5004)