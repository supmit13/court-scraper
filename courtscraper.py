import os, sys, re, time, gzip
import urllib, urllib2, httplib
from BeautifulSoup import BeautifulSoup
from urlparse import urlparse, urlsplit
from StringIO import StringIO
import datetime
#from threading import Thread
#import thread, random


"""
Some utility function definitions
"""
def urlEncodeString(s):
    tmphash = {'str' : s }
    encodedStr = urllib.urlencode(tmphash)
    encodedPattern = re.compile(r"^str=(.*)$")
    encodedSearch = encodedPattern.search(encodedStr)
    encodedStr = encodedSearch.groups()[0]
    encodedStr = encodedStr.replace('.', '%2E')
    encodedStr = encodedStr.replace('-', '%2D')
    encodedStr = encodedStr.replace(',', '%2C')
    return (encodedStr)


def encode_multipart_formdata(fields):
    BOUNDARY = mimetools.choose_boundary()
    CRLF = '\r\n'
    L = []
    for (key, value) in fields.iteritems():
        L.append('--' + BOUNDARY)
        L.append('Content-Disposition: form-data; name="%s"' % key)
        L.append('')
        L.append(value)
    L.append('--' + BOUNDARY + '--')
    L.append('')
    body = CRLF.join(L)
    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
    content_length = str(len(body))
    return content_type, content_length, body


def getTimeStampString():
    ts = time.time()
    ts_str = int(ts).__str__()
    return (ts_str)


class NoRedirectHandler(urllib2.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        infourl = urllib.addinfourl(fp, headers, req.get_full_url())
        infourl.status = code
        infourl.code = code
        return infourl

    http_error_300 = http_error_302
    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302 




class Bot(object):
    absUrlPattern = re.compile(r"^https?:\/\/", re.IGNORECASE)
    htmlTagPattern = re.compile(r"<[^>]+>", re.MULTILINE | re.DOTALL)
    newlinePattern = re.compile(r"\n")
    multipleWhitespacePattern = re.compile(r"\s+")
    pathEndingWithSlashPattern = re.compile(r"\/$")
    emptyStringPattern = re.compile(r"^\s*$", re.MULTILINE | re.DOTALL)

    caseDetailsPageRequestQueue = []
    caseDetailsPageURL = "https://www.courts.mo.gov/casenet/cases/header.do"
    htmlEntitiesDict = {'&nbsp;' : ' ', '&#160;' : ' ', '&amp;' : '&', '&#38;' : '&', '&lt;' : '<', '&#60;' : '<', '&gt;' : '>', '&#62;' : '>', '&apos;' : '\'', '&#39;' : '\'', '&quot;' : '"', '&#34;' : '"'}
    # Set DEBUG to False on prod env
    DEBUG = True

    targetCourts = ['OSCDB0013_FCC', 'SMPDB0001_CT05', 'SMPDB0001_CT06', 'SMPDB0001_CT07', 'SMPDB0004_CT11', 'SMPDB0004_CT13', 'SMPDB0001_CT15', 'SMPDB0017_CT16', 'SMPDB0001_CT17', 'SMPDB0001_CT18', 'OSCDB0024_CT19', 'SMPDB0009_CT21', 'SMPDB0010_CT22', 'SMPDB0004_CT23', 'SMPDB0005_CT31']

    availableCourts = []

    def __init__(self, siteUrl, n):
        self.opener = urllib2.build_opener() # This is my normal opener....
        self.no_redirect_opener = urllib2.build_opener(urllib2.HTTPHandler(), urllib2.HTTPSHandler(), NoRedirectHandler()) # this one won't handle redirects.
        #self.debug_opener = urllib2.build_opener(urllib2.HTTPHandler(debuglevel=1))
        # Initialize some object properties.
        self.daysNumBack = n
        self.sessionCookies = ""
        self.httpHeaders = { 'User-Agent' : r'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.110 Safari/537.36',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language' : 'en-US,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate,sdch', 'Connection' : 'keep-alive', 'Host' : 'www.courts.mo.gov' }
        self.homeDir = os.getcwd()
        self.websiteUrl = siteUrl
        self.requestUrl = self.websiteUrl
        self.baseUrl = None
        self.pageRequest = None
        self.isCriminal = False
        # This will be a hash with 'Case Number' as the key and the URL to the case as the value,
        # and at the second level it will store the 'Parties' and 'Charges' as keys and the values
        # in them as the values.
        self.cases = {} 
        if self.websiteUrl:
            parsedUrl = urlparse(self.requestUrl)
            self.baseUrl = parsedUrl.scheme + "://" + parsedUrl.netloc
            # Here we just get the webpage pointed to by the website URL
            self.pageRequest = urllib2.Request(self.requestUrl, None, self.httpHeaders)
        self.pageResponse = None
        self.requestMethod = "GET"
        self.postData = {}
        self.sessionCookies = None
        self.currentPageContent = None
        if self.websiteUrl:
            try:
                self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                self.sessionCookies = self.__class__._getCookieFromResponse(self.pageResponse)
                self.httpHeaders["Cookie"] = self.sessionCookies
            except:
                print __file__.__str__() + ": Couldn't fetch page due to limited connectivity. Please check your internet connection and try again - %s\n"%(sys.exc_info()[1].__str__())
	    	return(None)
            self.httpHeaders["Referer"] = self.requestUrl
            self.httpHeaders["Cache-Control"] = 'max-age=0'
            self.httpHeaders["Origin"] = 'https://www.courts.mo.gov'
            self.httpHeaders["Content-Type"] = 'application/x-www-form-urlencoded'
            # Initialize the account related variables...
            self.currentPageContent = self.__class__._decodeGzippedContent(self.getPageContent())
            if not self.currentPageContent:
                print "Could not access the website content of " + self.websiteUrl
            

    """
    Cookie extractor method to get cookie values from the HTTP response objects. (class method)
    """
    def _getCookieFromResponse(cls, lastHttpResponse):
        cookies = ""
        lastResponseHeaders = lastHttpResponse.info()
        responseCookies = lastResponseHeaders.getheaders("Set-Cookie")
        pathCommaPattern = re.compile(r"path=/\s*;?", re.IGNORECASE)
        domainPattern = re.compile(r"Domain=[^;]+;?", re.IGNORECASE)
        expiresPattern = re.compile(r"Expires=[^;]+;?", re.IGNORECASE)
	deletedPattern = re.compile(r"=deleted;", re.IGNORECASE)
        if responseCookies.__len__() >= 1:
            for cookie in responseCookies:
                cookieParts = cookie.split("Path=/")
                cookieParts[0] = re.sub(domainPattern, "", cookieParts[0])
                cookieParts[0] = re.sub(expiresPattern, "", cookieParts[0])
		deletedSearch = deletedPattern.search(cookieParts[0])
		if deletedSearch:
		    continue
                cookies += "; " + cookieParts[0]
	    multipleWhiteSpacesPattern = re.compile(r"\s+")
	    cookies = re.sub(multipleWhiteSpacesPattern, " ", cookies)
	    multipleSemicolonsPattern = re.compile(";\s*;")
	    cookies = re.sub(multipleSemicolonsPattern, "; ", cookies)
	    if re.compile("^\s*;").search(cookies):
		cookies = re.sub(re.compile("^\s*;"), "", cookies)
            return(cookies)
	else:
	    return(None)
    
    _getCookieFromResponse = classmethod(_getCookieFromResponse)


    def _decodeGzippedContent(cls, encoded_content):
        response_stream = StringIO(encoded_content)
        decoded_content = ""
        try:
            gzipper = gzip.GzipFile(fileobj=response_stream)
            decoded_content = gzipper.read()
        except: # Maybe this isn't gzipped content after all....
            decoded_content = encoded_content
        return(decoded_content)

    _decodeGzippedContent = classmethod(_decodeGzippedContent)


    def getPageContent(self):
        if self.pageResponse:
            content = self.pageResponse.read()
            self.currentPageContent = content
            # Remove the line with 'DOCTYPE html PUBLIC' string. It sometimes causes BeautifulSoup to fail in parsing the html
            #self.currentPageContent = re.sub(r"<.*DOCTYPE\s+html\s+PUBLIC[^>]+>", "", content)
            return(self.currentPageContent)
        else:
            return None


    def parseSearchForm(self):
        html = self.currentPageContent
        soup = BeautifulSoup(html)
        searchForm = soup.find("form", {'name' : 'filingDateSearchForm'})
        allhiddens = searchForm.findAll("input", {'type' : 'hidden'})
        form = {}
        form['action'] = searchForm['action']
        form['method'] = searchForm['method']
        for hidden in allhiddens:
            form[hidden['name']] = hidden['value']
        courtSelect = searchForm.find("select", {'name' : 'courtId'})
        allOptions = courtSelect.findAll("option")
        form['courtId'] = ""
        self.__class__.availableCourts = []
        for opt in allOptions:
            if not opt['value'] in self.__class__.targetCourts:
                continue
            self.__class__.availableCourts.append(opt['value'])
        dateText = searchForm.find("input", {'type' : 'text'})
        date_N = self.__class__._getNDaysBack(self.daysNumBack)
        form[dateText['name']] = date_N
        form['inputVO.caseStatus'] = 'A'
        form['findButton'] = 'Find'
        form['inputVO.courtId'] = form['courtId']
        form['inputVO.selectionAction'] = "search"
        form['inputVO.courtDesc'] = "Supreme Court"
        return form


    def _getNDaysBack(cls, N):
        now = time.time()
        NDays = N*86400
        NDaysBack = now - NDays
        dateNDaysBack = datetime.datetime.fromtimestamp(NDaysBack).strftime('%m/%d/%Y')
        return(dateNDaysBack)
    _getNDaysBack = classmethod(_getNDaysBack)


    def _getApproxNumRecords(cls, content):
        soup = BeautifulSoup(content)
        allAnchors = soup.findAll(r"a", {'href' : re.compile('javascript:goToThisPage\(\d+\);')})
        maxPage = 1
        for anchor in allAnchors:
            anchorText = anchor.getText()
            anchorText = anchorText.strip()
            numPattern = re.compile(r"(\d+)")
            rangePattern = re.compile(r"\[Next\s+\d+\s+of\s+(\d+)\]", re.DOTALL | re.MULTILINE)
            numSrch = numPattern.search(anchorText)
            rangeSrch = rangePattern.search(anchorText)
            if numSrch:
                maxPage = numSrch.groups()[0]
            elif rangeSrch:
                maxPage = rangeSrch.groups()[0]
                break
        totalCount = int(maxPage) * 15
        return totalCount
    _getApproxNumRecords = classmethod(_getApproxNumRecords)


    def printCsvHeader(cls, fw):
        fw.write("\"Name\", \"Case Title\", \"Location\", \"Date Filed\", \"Charges Description\", \"Charges Date\", \"Party Represented\", \"Street\", \"City\", \"State\", \"ZIP Code\", \"Plaintiff/Respondent Name\", \"Plaintiff/Respondent Address\", \"Defendant Name\", \"Defendant Address - Street\", \"Defendant Address - City\", \"Defendant Address - State\", \"Defendant Address - ZIP\", \"IsDefendantRepresented\", \"Judge/Commissioner Assigned\", \"Case Type\"\n")
        fw.flush()
        
    printCsvHeader = classmethod(printCsvHeader)


    def retrieveData(self, civil):
        form = self.parseSearchForm()
        self.httpHeaders['Referer'] = self.requestUrl
        self.requestUrl = self.baseUrl + form['action']
        for court in self.__class__.availableCourts:
            print "Processing " + court + "...\n"
            courtFilename = "data" + os.path.sep + court.replace(" ", "_") + ".csv"
            fcw = open(courtFilename, "w")
            #fcw.flush()
            self.__class__.printCsvHeader(fcw)
            for field in form.keys():
                if field == 'method' or field == 'action':
                    continue
                self.postData[field] = form[field]
            self.postData['courtId'] = court
            self.postData['inputVO.courtId'] = self.postData['courtId']
            self.postData['inputVO.caseType'] = 'All'
            if civil:
                self.postData['inputVO.caseType'] = 'Civil'
            encodedPostData = urllib.urlencode(self.postData)
            self.httpHeaders['Content-Length'] = encodedPostData.__len__()
            self.pageRequest = urllib2.Request(self.requestUrl, encodedPostData, self.httpHeaders)
            requestSuccessFlag1 = 0
            while not requestSuccessFlag1:
                try:
                    self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                    requestSuccessFlag1 = 1
                except:
                    print __file__.__str__() + ": The connection is not working right now... Will wait for a little while before trying again. - %s\n"%(sys.exc_info()[1].__str__())
                    time.sleep(10)
            content = self.__class__._decodeGzippedContent(self.getPageContent()) # This is the first page
            soup = BeautifulSoup(content)
            #approxNumRecords = self.__class__._getApproxNumRecords(content)
            try:
                pageForm = soup.find("form", {'name' : 'filingDateSearchForm'})
                totalRecords = pageForm.find("input", {'name' : 'inputVO.totalRecords'})['value']
                allHiddenTags = pageForm.findAll("input", {'type' : 'hidden'})
            except:
                print "Encountered problem in parsing 'filingDateSearchForm' (probably because there are no records to parse) - %s\n"%(sys.exc_info()[1].__str__())
                continue
            print "Counting records...  %s\n"%totalRecords
            pageFormData = {}
            pageAction = "https://www.courts.mo.gov" + pageForm['action']
            for hiddenTag in allHiddenTags:
                pageFormData[hiddenTag['name']] = hiddenTag['value']
            nextPageStartRecord = 1
            while int(nextPageStartRecord) <= int(totalRecords):
                self._getCasesList(content)
                nextPageStartRecord += 15
                pageFormData['inputVO.startingRecord'] = nextPageStartRecord
                encodedPageFormData = urllib.urlencode(pageFormData)
                self.requestUrl = pageAction
                self.httpHeaders['Content-Length'] = encodedPageFormData.__len__()
                self.pageRequest = urllib2.Request(self.requestUrl, encodedPageFormData, self.httpHeaders)
                requestSuccessFlag2 = 0
                while not requestSuccessFlag2:
                    try:
                        self.pageResponse = self.no_redirect_opener.open(self.pageRequest)
                        requestSuccessFlag2 = 1
                    except:
                        print "The internet connection is having problems right now. Will try again after a little while - %s\n"%(sys.exc_info()[1].__str__())
                        time.sleep(10)
                content = self.__class__._decodeGzippedContent(self.getPageContent())
            # At this point, 'self.__class__.caseDetailsPageRequestQueue' contains the HTTP request objects for the currently processing court.
            while True:
                if self.__class__.caseDetailsPageRequestQueue.__len__() == 0:
                    break
                requestObj = self.__class__.caseDetailsPageRequestQueue.pop()
                requestSuccessFlag3 = 0
                responseContent = ""
                while not requestSuccessFlag3:
                    try:
                        responseObj = self.no_redirect_opener.open(requestObj)
                        responseContent = self.__class__._decodeGzippedContent(responseObj.read())
                        requestSuccessFlag3 = 1
                    except:
                        print "The internet connection is having problems right now. Will try again in a little while - %s\n"%(sys.exc_info()[1].__str__())
                        time.sleep(10)
                # Now parse the retrieved page to extract the desired information.
                soup = BeautifulSoup(responseContent)
                (name, caseTitle, location, dateFiled, charges, parties, judgeCommissionerAssigned) = "", "", "", "", {}, {}, ""
                caseTitleTD = soup.find("td", {'class' : 'searchType'})
                if not caseTitleTD:
                    continue
                caseTitle = caseTitleTD.getText()
                for entity in self.__class__.htmlEntitiesDict.keys():
                    caseTitle = caseTitle.replace(entity, self.__class__.htmlEntitiesDict[entity])
                detailTDs = soup.findAll("td", {'class' : re.compile("detail")})
                locFlag = False
                dateFiledFlag = False
                isCriminal = self.isCriminal
                caseTypeFlag = False
                caseType = ""
                judgeCommissionerFlag = False
                for detTD in detailTDs:
                    if detTD["class"] == "detailLabels":
                        contentLabel = detTD.getText()
                        contentLabel = re.sub(self.__class__.multipleWhitespacePattern, " ", contentLabel)
                        if contentLabel.strip() == "Location:":
                            locFlag = True
                            continue
                        if contentLabel.strip() == "Date Filed:":
                            dateFiledFlag = True
                            continue
                        if contentLabel.strip() == "Case Type:":
                            caseTypeFlag = True
                            continue
                        if contentLabel.strip() == "Judge/Commissioner At Disposition:" or contentLabel.strip() == "Judge/Commissioner Assigned:":
                            judgeCommissionerFlag = True
                            continue
                    if locFlag and detTD["class"] == "detailData":
                        location = detTD.getText()
                        location = re.sub(self.__class__.multipleWhitespacePattern, " ", location)
                        location = re.sub(re.compile(r","), "__comma__", location)
                        locFlag = False
                    elif dateFiledFlag and detTD["class"] == "detailData":
                        dateFiled = detTD.getText()
                        dateFiled = re.sub(self.__class__.multipleWhitespacePattern, " ", dateFiled)
                        dateFiledFlag = False
                    elif caseTypeFlag and detTD["class"] == "detailData":
                        caseType = detTD.getText()
                        caseType = re.sub(self.__class__.multipleWhitespacePattern, " ", caseType)
                        caseTypeFlag = False
                    elif judgeCommissionerFlag and detTD["class"] == "detailData":
                        judgeCommissionerAssigned = detTD.getText()
                        judgeCommissionerAssigned = re.sub(self.__class__.multipleWhitespacePattern, " ", judgeCommissionerAssigned)
                        judgeCommissionerAssigned = re.sub(re.compile(r","), "__comma__", judgeCommissionerAssigned)
                        judgeCommissionerFlag = False
                        # The following logic is useful when we are extracting data with 'inputVO.caseType' set to 'All'.
                        # In such cases we will be getting some 'Civil' cases and some 'Criminal' cases. We differntiate
                        # between the two cases using the variable 'isCriminal'. This case is different from data extrac-
                        # tion with 'inputVO.caseType' set to 'Civil'.
                    criminalPattern = re.compile(r"Criminal", re.IGNORECASE | re.DOTALL | re.MULTILINE)
                    if criminalPattern.search(caseType):
                        isCriminal = True
                        self.isCriminal = True
                    else:
                        isCriminal = False # This means this is a civil case. So we need to handle it differently.
                charges = self._getCharges(responseContent)
                parties = self._getParties(responseContent)
                caseTitle = re.sub(re.compile(r","), "__comma__", caseTitle)
                if not parties.has_key('street'):
                    parties['street'] = ""
                parties['street'] = self.__class__._removeStateZip(parties['street'])
                line = "\"" + parties['name'] + "\", \"" + caseTitle + "\", \"" + location + "\", \"" + dateFiled + "\", \"" + charges['description'] + "\", \"" + charges['date'] + "\", \"" + parties['isDefendantRepresented'] + "\", \"" + parties['street'] + "\", \"" + parties['city'] + "\", \"" + parties['state'] + "\", \"" + parties['zip'] + "\", \"" + parties['plaintiff'] + "\", \"" + parties['plaintiff_address'] + "\", \"" + parties['defendant'] + "\", \"" + parties['defendant_address_street'] + "\", \"" + parties['defendant_address_city'] + "\", \"" + parties['defendant_address_state'] + "\", \"" + parties['defendant_address_zip'] + "\", \"" + parties['isDefendantRepresented'] + "\", \"" + judgeCommissionerAssigned + "\", \"" + caseType + "\""
                line = line + "\n"
                fcw.write(line)
                fcw.flush()
                
        fcw.close()



    def _removeStateZip(cls, street):
        streetParts = street.split('__comma__')
        if streetParts.__len__() > 1:
            streetParts.pop()
            return('__comma__'.join(streetParts))
        else:
            return(street)

    _removeStateZip = classmethod(_removeStateZip)
    

    def _getCharges(self, pageContent):
        noChargesPattern = re.compile(r"Charge\s+information\s+is\s+not\s+available\s+for\s+the\s+selected\s+case")
        charges = {'description' : '', 'date' : '', 'ocn' : '', 'code' : '', 'ticketno' : ''}
        if noChargesPattern.search(pageContent):
            return(charges)
        soup = BeautifulSoup(pageContent)
        try:
            casePalletteForm = soup.find("form", {'name' : 'casePalletteForm'})
            allHiddenTags = casePalletteForm.findAll("input", {'type' : 'hidden'})
        except:
            print "Could not parse 'casePalletteForm' - %s\n"%(sys.exc_info()[1].__str__())
            return (charges)
        postData = {}
        for hiddenTag in allHiddenTags:
            postData[hiddenTag['name']] = hiddenTag['value']
        chargesTabUrl = "https://www.courts.mo.gov/casenet/cases/charges.do"
        chargesTabRequestHeaders = {}
        for hdrname in self.httpHeaders.keys():
            chargesTabRequestHeaders[hdrname] = self.httpHeaders[hdrname]
            if hdrname == "Content-Length":
                chargesTabRequestHeaders[hdrname] = urllib.urlencode(postData).__len__()
        chargesTabRequest = urllib2.Request(chargesTabUrl, urllib.urlencode(postData), chargesTabRequestHeaders)
        try:
            chargesTabResponse = self.no_redirect_opener.open(chargesTabRequest)
            chargesTabResponseContent = self.__class__._decodeGzippedContent(chargesTabResponse.read())
        except:
            print "Could not fetch contents of 'Charges, Judgements & Sentences' tab - %s\n"%(sys.exc_info()[1].__str__())
            return (charges)
        chargesSoup = BeautifulSoup(chargesTabResponseContent)
        try:
            allTds = chargesSoup.findAll('td', {'class' : 'detailLabels'})
        except:
            print "Could not parse contents of 'Charges, Judgements & Sentences' tab - %s\n"%(sys.exc_info()[1].__str__())
            return (charges)
        for td in allTds:
            if td.getText() == "Description:":
                nextTd = td.findNext("td")
                charges['description'] = nextTd.getText()
                for entity in self.__class__.htmlEntitiesDict.keys():
                    charges['description'] = charges['description'].replace(entity, self.__class__.htmlEntitiesDict[entity])
                charges['description'] = charges['description'].replace(",", "__comma__")
            if td.getText() == "Date:":
                nextTd = td.findNext("td")
                charges['date'] = nextTd.getText()
                for entity in self.__class__.htmlEntitiesDict.keys():
                    charges['date'] = charges['date'].replace(entity, self.__class__.htmlEntitiesDict[entity])
        return(charges)


    def _getParties(self, pageContent):
        soup = BeautifulSoup(pageContent)
        parties = { 'name' : '', 'info' : '', 'street' : '', 'city' : '', 'state' : '', 'zip' : '',  'defendant' : '', 'defendant_address_street' : '', 'defendant_address_city' : '', 'defendant_address_state' : '', 'defendant_address_zip' : '', 'plaintiff' : '', 'plaintiff_address' : '', 'isDefendantRepresented' : '' }
        try:
            casePalletteForm = soup.find("form", {'name' : 'casePalletteForm'})
            allHiddenTags = casePalletteForm.findAll("input", {'type' : 'hidden'})
        except:
            print "Could not parse casePalletteForm - %s\n"%(sys.exc_info()[1].__str__())
            return(parties) # Return empty parties
        postData = {}
        for hiddenTag in allHiddenTags:
            postData[hiddenTag['name']] = hiddenTag['value']
        partiesTabUrl = "https://www.courts.mo.gov/casenet/cases/parties.do"
        partiesTabRequestHeaders = {'info' : ''}
        for hdrname in self.httpHeaders.keys():
            partiesTabRequestHeaders[hdrname] = self.httpHeaders[hdrname]
            if hdrname == "Content-Length":
                partiesTabRequestHeaders[hdrname] = urllib.urlencode(postData).__len__()
        partiesTabRequest = urllib2.Request(partiesTabUrl, urllib.urlencode(postData), partiesTabRequestHeaders)
        try:
            partiesTabResponse = self.no_redirect_opener.open(partiesTabRequest)
            partiesTabResponseContent = self.__class__._decodeGzippedContent(partiesTabResponse.read())
        except:
            print "Could not fetch contents of 'Parties & Attorneys' tab - %s\n"%(sys.exc_info()[1].__str__())
            return (parties)
        tdctr = 0
        try:
            partiesSoup = BeautifulSoup(partiesTabResponseContent)
            table = partiesSoup.find("table", {'class' : 'detailRecordTable'})
            allTds = table.findAll("td")
        except:
            print "Could not parse contents of 'Parties & Attorneys' tab. - %s\n"%(sys.exc_info()[1].__str__())
            return(parties) # Return empty parties
        htmlTagPattern = re.compile(r"<\/?[^>]+\s*\/?>")
        plaintiff_represented = "No"
        if self.isCriminal:
            defendant_address = ""
            defendant_address_street = ""
            defendant_address_city = ""
            defendant_address_state = ""
            defendant_address_zip = ""
            defendant_represented = ""
            for td in allTds:
                if tdctr == 0: # First td contains the name
                    parties['name'] = td.getText().strip()
                elif tdctr == 2:
                    plaintiff_attorney = td.getText().strip()
                    plaintiff_attorney = re.sub(re.compile(r"&nbsp;"), " ", plaintiff_attorney)
                    plaintiff_attorney = re.sub(htmlTagPattern, "", plaintiff_attorney)
                    plaintiff_attorney = re.sub(re.compile(r"\s+"), " ", plaintiff_attorney)
                    attorney_pattern = re.compile(r", Attorney\s+for\s+Plaintiff", re.IGNORECASE | re.MULTILINE | re.DOTALL)
                    respondent_pattern = re.compile(r", Attorney\s+for\s+Respondent", re.IGNORECASE | re.MULTILINE | re.DOTALL)
                    if attorney_pattern.search(plaintiff_attorney) or plaintiff_attorney != "":
                        plaintiff_represented = "Yes"
                elif tdctr == 3:
                    parties['info'] += td.renderContents().strip()
                    plaintiff_address = parties['info']
                elif tdctr == 6:
                    parties['defendant'] = td.renderContents().strip()
                    parties['defendant'] = re.sub(re.compile(r"&nbsp;"), " ", parties['defendant'])
                    parties['defendant'] = re.sub(self.__class__.multipleWhitespacePattern, " ", parties['defendant'])
                    parties['defendant'] = re.sub(re.compile(r","), "__comma__", parties['defendant'])
                elif tdctr == 9:
                    defendant_address = td.renderContents().strip()
                    defendant_address_broken = defendant_address.split("<br />")
                    defendant_address_citystatezip = ''
                    defendant_address_street = defendant_address_broken[0]
                    city_state_zip_pattern = re.compile(r"\s+([\w\s]*)\,\s+(\w{2})\s+(\d{4,5})", re.MULTILINE | re.DOTALL)
                    # To find out which element contains the city, state, zip info, we will look for the 'city_state_zip_pattern' in the elements
                    for addr_element in defendant_address_broken:
                        pattern_match = city_state_zip_pattern.search(addr_element)
                        if pattern_match:
                            defendant_address_citystatezip = addr_element
                            break
                    if not defendant_address_citystatezip:
                        defendant_address_citystatezip = defendant_address_broken[defendant_address_broken.__len__() - 2]
                    if defendant_address_broken.__len__() >= 2:
                        city_state_zip_search = city_state_zip_pattern.search(defendant_address_broken[1])
                        if not city_state_zip_search:
                            defendant_address_street = defendant_address_broken[0] + defendant_address_broken[1]
                        else:
                            defendant_address_street = defendant_address_broken[0]
                    else:
                        defendant_address_street = defendant_address_broken[0]
                    defendant_address_street = re.sub(re.compile(r"&nbsp;"), " ", defendant_address_street)
                    defendant_address_street = re.sub(htmlTagPattern, " ", defendant_address_street)
                    defendant_address_street = re.sub(re.compile(r"\s+"), " ", defendant_address_street)
                    defendant_address_street = re.sub(re.compile(r","), "__comma__", defendant_address_street)
                    defendant_address_street = re.sub(re.compile(r"__comma__.*$"), "", defendant_address_street)
                    city_state_zip_match = city_state_zip_pattern.search(defendant_address_citystatezip)
                    city_state_zip = []
                    if city_state_zip_match:
                        city_state_zip = city_state_zip_match.groups()
                    if city_state_zip.__len__() >= 1:
                        defendant_address_city = city_state_zip[0]
                    if city_state_zip.__len__() >= 2:
                        defendant_address_state = city_state_zip[1]
                    if city_state_zip.__len__() >= 3:
                        defendant_address_zip = city_state_zip[2]
                    defendant_address_city = re.sub(re.compile(r"&nbsp;"), " ", defendant_address_city)
                    defendant_address_city = re.sub(htmlTagPattern, " ", defendant_address_city)
                    defendant_address_city = re.sub(re.compile(r"\s+"), " ", defendant_address_city)
                    defendant_address_city = re.sub(re.compile(r","), "__comma__", defendant_address_city)
                    defendant_address_state = re.sub(re.compile(r"&nbsp;"), " ", defendant_address_state)
                    defendant_address_state = re.sub(htmlTagPattern, " ", defendant_address_state)
                    defendant_address_state = re.sub(re.compile(r"\s+"), " ", defendant_address_state)
                    defendant_address_zip = re.sub(re.compile(r"&nbsp;"), " ", defendant_address_zip)
                    defendant_address_zip = re.sub(htmlTagPattern, " ", defendant_address_zip)
                    defendant_address_zip = re.sub(re.compile(r"\s+"), " ", defendant_address_zip)
                    parties['defendant_address_street'] = defendant_address_street
                    parties['defendant_address_city'] = defendant_address_city
                    parties['defendant_address_state'] = defendant_address_state
                    parties['defendant_address_zip'] = defendant_address_zip
                tdctr += 1
            parties['info'] = re.sub(re.compile(r"&nbsp;"), " ", parties['info'])
            parties['info'] = re.sub(self.__class__.multipleWhitespacePattern, " ", parties['info'])
            parties['info'] = re.sub(re.compile(r"<b>Year\s+of\s+Birth\:\s+</b>\s*\d{4}"), "", parties['info'])
            for entity in self.__class__.htmlEntitiesDict.keys():
                parties['info'] = parties['info'].replace(entity, self.__class__.htmlEntitiesDict[entity])
            info_parts = parties['info'].split("<br />")
            parties['street'] = info_parts[0]
            if info_parts.__len__() > 1:
                parties['street'] = info_parts[0] + " " + info_parts[1]
            parties['street'] = re.sub(self.__class__.multipleWhitespacePattern, " ", parties['street'])
            parties['street'] = re.sub(re.compile(r","), "__comma__", parties['street'])
            city_state_zip = ""
            if info_parts.__len__() > 2:
                city_state_zip = info_parts[2].strip()
            emptyStringPattern = re.compile(r"^\s*$")
            if emptyStringPattern.search(city_state_zip) and info_parts.__len__() > 1:
                city_state_zip = info_parts[1].strip()
            city_and_state_zip = city_state_zip.split(",")
            city = city_and_state_zip[0]
            state_zip = ""
            if city_and_state_zip.__len__() > 1:
                state_zip = city_and_state_zip[1]
            state_zip = re.sub(re.compile(r"\s+"), " ", state_zip)
            state_zip = state_zip.strip()
            state_and_zip = state_zip.split(" ")
            state = state_and_zip[0]
            zip = ""
            if state_and_zip.__len__() > 1:
                zip = state_and_zip[1]
            parties['state'] = state.strip()
            parties['city'] = city.strip()
            parties['zip'] = zip.strip()
            parties['name'] = re.sub(re.compile(r"&nbsp;"), " ", parties['name'])
            parties['name'] = re.sub(self.__class__.multipleWhitespacePattern, " ", parties['name'])
            parties['plaintiff'] = parties['name']
            parties['plaintiff'] = re.sub(re.compile(r","), "__comma__", parties['plaintiff'])
            parties['plaintiff_address'] = parties['info']
            parties['plaintiff_address'] = re.sub(re.compile(r","), "__comma__", parties['plaintiff_address'])
            parties['plaintiff_address'] = re.sub(re.compile(r"<\/?[^>]+\s*\/?>"), "", parties['plaintiff_address'])
            parties['street'] = parties['street'].replace(entity, self.__class__.htmlEntitiesDict[entity])
            # Remove city name from street address
            parties['street'] = parties['street'].replace(parties['city'], "")
            for entity in self.__class__.htmlEntitiesDict.keys():
                parties['name'] = parties['name'].replace(entity, self.__class__.htmlEntitiesDict[entity])
            parties['isDefendantRepresented'] = "NA" # For 'Not Applicable'
        else: # Handling 'Civil' cases
            plaintiff = allTds[0].getText().strip()
            plaintiff = re.sub(re.compile(r"&nbsp;"), " ", plaintiff)
            plaintiff = re.sub(self.__class__.multipleWhitespacePattern, " ", plaintiff)
            parties['name'] = plaintiff
            plaintiff_attorney = allTds[2].getText().strip()
            plaintiff_attorney = re.sub(re.compile(r"&nbsp;"), " ", plaintiff_attorney)
            plaintiff_attorney = re.sub(htmlTagPattern, "", plaintiff_attorney)
            plaintiff_represented = "No"
            attorney_pattern = re.compile(r", Attorney\s+for\s+Plaintiff", re.IGNORECASE | re.MULTILINE | re.DOTALL)
            respondent_pattern = re.compile(r", Attorney\s+for\s+Respondent", re.IGNORECASE | re.MULTILINE | re.DOTALL)
            plaintiff_address = allTds[3].renderContents().strip()
            plaintiff_address = re.sub(re.compile(r"&nbsp;"), " ", plaintiff_address)
            plaintiff_address = re.sub(re.compile(r"\s+"), " ", plaintiff_address)
            plaintiff_address = re.sub(re.compile(r"Year\s+of\s+Birth:\s+\d{4}", re.IGNORECASE | re.MULTILINE | re.DOTALL), "", plaintiff_address)
            if attorney_pattern.search(plaintiff_attorney) or plaintiff_attorney != "":
                plaintiff_represented = "Yes"
            parties['info'] = plaintiff_address
            parties['info'] = re.sub(re.compile(r"<b>Year\s+of\s+Birth\:\s+</b>\s*\d{4}"), "", parties['info'])
            info_parts = parties['info'].split("<br />")
            parties['street'] = info_parts[0]
            stateZipPattern = re.compile(r"\,\s+\w{2}\s+\d{5}\-?", re.MULTILINE | re.DOTALL)
            if info_parts.__len__() > 1:
                if not stateZipPattern.search(info_parts[1]): # If 'info_parts[1]' does not contain the state and zip codes, but contain a part of the street address, we concatenate it.
                    parties['street'] = info_parts[0] + " " + info_parts[1]
            parties['street'] = re.sub(htmlTagPattern, " ", parties['street'])
            parties['street'] = re.sub(re.compile(r","), "__comma__", parties['street'])
            parties['street'] = re.sub(re.compile(r"\w+__comma__\w{2}\s+\d{4,5}$"), "", parties['street'])
            city_state_zip = ""
            if info_parts.__len__() > 2:
                city_state_zip = info_parts[2]
            emptyStringPattern = re.compile(r"^\s*$")
            if emptyStringPattern.search(city_state_zip) and info_parts.__len__() > 1:
                city_state_zip = info_parts[1].strip()
            city_state_zip = re.sub(htmlTagPattern, " ", city_state_zip)
            city_and_statezip = city_state_zip.split(",")
            city = city_and_statezip[0]
            state_zip = ""
            if city_and_statezip.__len__() > 1:
                state_zip = city_and_statezip[1]
            state_zip = re.sub(re.compile(r"\s+"), " ", state_zip)
            state_zip = state_zip.strip()
            state_and_zip = state_zip.split(" ")
            parties['state'] = state_and_zip[0].strip()
            parties['zip'] = ""
            if state_and_zip.__len__() > 1:
                parties['zip'] = state_and_zip[1].strip()
            parties['city'] = city.strip()
            defendant = ""
            defendant_represented = ""
            if allTds.__len__() >= 7: 
                defendant = allTds[6].getText().strip()
                defendant = re.sub(re.compile(r"&nbsp;"), " ", defendant)
                defendant = re.sub(re.compile(r"\s+"), " ", defendant)
                defendant = re.sub(re.compile(r","), "__comma__", defendant)
            parties['defendant'] = defendant
            defendant_address_street = ""
            defendant_address_city = ""
            defendant_address_state = ""
            defendant_address_zip = ""
            if allTds.__len__() >= 10:
                defendant_represented = allTds[8].renderContents().strip()
                defendant_represented = re.sub(re.compile(r"\s+", re.DOTALL | re.MULTILINE), " ", defendant_represented)
                defendant_represented = re.sub(re.compile(r"&nbsp;"), " ", defendant_represented)
                defendant_represented = re.sub(re.compile(r","), "__comma__", defendant_represented)
                defendant_address = allTds[9].renderContents().strip()
                defendant_address_broken = defendant_address.split("<br />")
                defendant_address_citystatezip = ''
                defendant_address_street = defendant_address_broken[0]
                city_state_zip_pattern = re.compile(r"\s+([\w\s]*)\,\s+(\w{2})\s+(\d{4,5})", re.MULTILINE | re.DOTALL)
                # To find out which element contains the city, state, zip info, we will look for the 'city_state_zip_pattern' in the elements
                for addr_element in defendant_address_broken:
                    pattern_match = city_state_zip_pattern.search(addr_element)
                    if pattern_match:
                        defendant_address_citystatezip = addr_element
                        break
                if not defendant_address_citystatezip:
                    defendant_address_citystatezip = defendant_address_broken[defendant_address_broken.__len__() - 2]
                    if defendant_address_broken.__len__() >= 2:
                        city_state_zip_search = city_state_zip_pattern.search(defendant_address_broken[1])
                        if not city_state_zip_search:
                            defendant_address_street = defendant_address_broken[0] + defendant_address_broken[1]
                        else:
                            defendant_address_street = defendant_address_broken[0]
                    else:
                        defendant_address_street = defendant_address_broken[0]
                defendant_address_street = re.sub(re.compile(r"&nbsp;"), " ", defendant_address_street)
                defendant_address_street = re.sub(htmlTagPattern, " ", defendant_address_street)
                defendant_address_street = re.sub(re.compile(r"\s+"), " ", defendant_address_street)
                defendant_address_street = re.sub(re.compile(r","), "__comma__", defendant_address_street)
                defendant_address_street = re.sub(re.compile(r"__comma__.*$"), "", defendant_address_street)
                city_state_zip_match = city_state_zip_pattern.search(defendant_address_citystatezip)
                city_state_zip = []
                if city_state_zip_match:
                    city_state_zip = city_state_zip_match.groups()
                if city_state_zip.__len__() >= 1:
                    defendant_address_city = city_state_zip[0]
                if city_state_zip.__len__() >= 2:
                    defendant_address_state = city_state_zip[1]
                if city_state_zip.__len__() >= 3:
                    defendant_address_zip = city_state_zip[2]
                defendant_address_city = re.sub(re.compile(r"&nbsp;"), " ", defendant_address_city)
                defendant_address_city = re.sub(htmlTagPattern, " ", defendant_address_city)
                defendant_address_city = re.sub(re.compile(r"\s+"), " ", defendant_address_city)
                defendant_address_city = re.sub(re.compile(r","), "__comma__", defendant_address_city)
                defendant_address_state = re.sub(re.compile(r"&nbsp;"), " ", defendant_address_state)
                defendant_address_state = re.sub(htmlTagPattern, " ", defendant_address_state)
                defendant_address_state = re.sub(re.compile(r"\s+"), " ", defendant_address_state)
                defendant_address_zip = re.sub(re.compile(r"&nbsp;"), " ", defendant_address_zip)
                defendant_address_zip = re.sub(htmlTagPattern, " ", defendant_address_zip)
                defendant_address_zip = re.sub(re.compile(r"\s+"), " ", defendant_address_zip)
            parties['defendant_address_street'] = defendant_address_street
            parties['defendant_address_city'] = defendant_address_city
            parties['defendant_address_state'] = defendant_address_state
            parties['defendant_address_zip'] = defendant_address_zip
            parties['defendant_address_street'] = re.sub(re.compile(r"Year\s+of\s+Birth:\d{4}"), "", parties['defendant_address_street'])
            parties['plaintiff'] = parties['name']
            parties['plaintiff'] = re.sub(re.compile(r","), "__comma__", parties['plaintiff'])
            parties['plaintiff_address'] = parties['info']
            parties['plaintiff_address'] = re.sub(re.compile(r"<\/?[^>]+\s*\/?>"), "", parties['plaintiff_address'])
            parties['plaintiff_address'] = re.sub(re.compile(r","), "__comma__", parties['plaintiff_address'])
            parties['isDefendantRepresented'] = defendant_represented
        return(parties)
        


    def _getCaseDetailsPageURL(self, content):
        soup = BeautifulSoup(content)
        caseDetailsForm = soup.find("form", {'name' : 'caseHeaderForm'})
        self.__class__.caseDetailsPageURL = caseDetailsForm['action']
        if not re.compile(r"^http://").search(self.__class__.caseDetailsPageURL):
            self.__class__.caseDetailsPageURL = "https://www.courts.mo.gov" + self.__class__.caseDetailsPageURL
    
    _getCaseDetailsPageURL = classmethod(_getCaseDetailsPageURL)


    # Takes the HTML content of the page and extracts the case names and the URLs to the details
    # of those cases. Handles multiple pages by traversing them as necessary.
    def _getCasesList(self, content):
        soup = BeautifulSoup(content)
        headers = {'User-Agent' : r'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.110 Safari/537.36',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language' : 'en-US,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate,sdch', 'Connection' : 'keep-alive', 'Host' : 'www.courts.mo.gov' }
        headers['Cookie'] = self.httpHeaders["Cookie"]
        headers['Referer'] = "https://www.courts.mo.gov/casenet/cases/filingDateSearch.do"
        headers['Content-Type'] = "application/x-www-form-urlencoded"
        if not self.__class__.caseDetailsPageURL:
            self.__class__._getCaseDetailsPageURL(content)
        hrefPattern = re.compile(r"javascript:goToThisCase\(\'([\w\-\d]+)\'\,\s+\'(\w+)\'\)")
        allAnchors = soup.findAll("a", {'href' : hrefPattern})
        for anchor in allAnchors:
            anchorMatch = hrefPattern.search(anchor.__str__())
            caseId, dbSource = anchorMatch.groups()[0], anchorMatch.groups()[1]
            postData = {'inputVO.caseNumber' : caseId, 'inputVO.courtId' : dbSource}
            headers['Content-Length'] = urllib.urlencode(postData).__len__()
            postRequest = urllib2.Request(self.__class__.caseDetailsPageURL, urllib.urlencode(postData), headers)
            self.__class__.caseDetailsPageRequestQueue.append(postRequest)




        
if __name__ == "__main__":
    numDays = sys.argv[1]
    civil = False
    if sys.argv.__len__() > 2:
        if sys.argv[2].lower() == "civil":
            civil = True
        else:
            print "Unrecognized parameter option - '%s'. Ignoring it...\n"%sys.argv[2]
    print "Processing for the last %s days\n"%numDays
    bot = Bot("https://www.courts.mo.gov/casenet/cases/searchCases.do?searchType=date", int(numDays))
    bot.retrieveData(civil)
    
