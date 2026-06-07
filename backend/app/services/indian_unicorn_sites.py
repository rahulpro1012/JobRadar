"""
JobRadar Tier 3a: Indian Unicorn Career Pages URLs

Maps Indian unicorn companies and other major Indian tech companies to their careers page URLs.
Used by SearxNG site: operator to discover jobs from their directly-hosted careers pages.

These are the ~35+ Indian companies that either don't use standard ATSes or maintain additional
direct career listings on their own websites.
"""

INDIAN_UNICORN_SITES = [
    # Fintech unicorns (10)
    {
        "name": "Razorpay",
        "site": "razorpay.com",
        "careers_url": "https://razorpay.com/careers/",
        "verified": True,
    },
    {
        "name": "PhonePe",
        "site": "phonepe.com",
        "careers_url": "https://phonepe.com/careers/",
        "verified": True,
    },
    {
        "name": "CRED",
        "site": "cred.club",
        "careers_url": "https://cred.club/careers/",
        "verified": True,
    },
    {
        "name": "Zerodha",
        "site": "zerodha.com",
        "careers_url": "https://zerodha.com/careers/",
        "verified": True,
    },
    {
        "name": "Groww",
        "site": "groww.in",
        "careers_url": "https://www.groww.in/careers/",
        "verified": True,
    },
    {
        "name": "Upstox",
        "site": "upstox.com",
        "careers_url": "https://careers.upstox.com/",
        "verified": True,
    },
    {
        "name": "Khatabook",
        "site": "khatabook.com",
        "careers_url": "https://khatabook.com/careers/",
        "verified": True,
    },
    {
        "name": "BharatPe",
        "site": "bharatpe.com",
        "careers_url": "https://bharatpe.com/careers/",
        "verified": True,
    },
    {
        "name": "Paytm",
        "site": "paytm.com",
        "careers_url": "https://paytm.com/careers/",
        "verified": True,
    },
    {
        "name": "Navi",
        "site": "navi.com",
        "careers_url": "https://navi.com/careers/",
        "verified": True,
    },

    # E-commerce/Delivery unicorns (12)
    {
        "name": "Swiggy",
        "site": "swiggy.com",
        "careers_url": "https://careers.swiggy.com/",
        "verified": True,
    },
    {
        "name": "Zomato",
        "site": "zomato.com",
        "careers_url": "https://www.zomato.com/careers/",
        "verified": True,
    },
    {
        "name": "Meesho",
        "site": "meesho.com",
        "careers_url": "https://meesho.com/careers/",
        "verified": True,
    },
    {
        "name": "Flipkart",
        "site": "flipkart.com",
        "careers_url": "https://www.flipkart.com/careers/",
        "verified": True,
    },
    {
        "name": "Nykaa",
        "site": "nykaa.com",
        "careers_url": "https://www.nykaa.com/careers/",
        "verified": True,
    },
    {
        "name": "BigBasket",
        "site": "bigbasket.com",
        "careers_url": "https://www.bigbasket.com/careers/",
        "verified": True,
    },
    {
        "name": "Blinkit",
        "site": "blinkit.com",
        "careers_url": "https://www.blinkit.com/careers/",
        "verified": True,
    },
    {
        "name": "Zepto",
        "site": "zepto.com",
        "careers_url": "https://zepto.com/careers/",
        "verified": True,
    },
    {
        "name": "Delhivery",
        "site": "delhivery.com",
        "careers_url": "https://www.delhivery.com/careers/",
        "verified": True,
    },
    {
        "name": "Urban Company",
        "site": "urbancompany.com",
        "careers_url": "https://www.urbancompany.com/careers",
        "verified": True,
    },
    {
        "name": "MakeMyTrip",
        "site": "makemytrip.com",
        "careers_url": "https://www.makemytrip.com/careers/",
        "verified": True,
    },
    {
        "name": "Ixigo",
        "site": "ixigo.com",
        "careers_url": "https://www.ixigo.com/careers/",
        "verified": True,
    },

    # SaaS/DevTools unicorns (8)
    {
        "name": "Freshworks",
        "site": "freshworks.com",
        "careers_url": "https://www.freshworks.com/careers/",
        "verified": True,
    },
    {
        "name": "Zoho",
        "site": "zoho.com",
        "careers_url": "https://www.zoho.com/careers/",
        "verified": True,
    },
    {
        "name": "BrowserStack",
        "site": "browserstack.com",
        "careers_url": "https://www.browserstack.com/careers/",
        "verified": True,
    },
    {
        "name": "Chargebee",
        "site": "chargebee.com",
        "careers_url": "https://www.chargebee.com/careers/",
        "verified": True,
    },
    {
        "name": "Icertis",
        "site": "icertis.com",
        "careers_url": "https://www.icertis.com/careers/",
        "verified": True,
    },
    {
        "name": "Druva",
        "site": "druva.com",
        "careers_url": "https://www.druva.com/company/careers/",
        "verified": True,
    },
    {
        "name": "Setu",
        "site": "setu.co",
        "careers_url": "https://setu.co/careers/",
        "verified": True,
    },
    {
        "name": "Moengage",
        "site": "moengage.com",
        "careers_url": "https://www.moengage.com/careers/",
        "verified": True,
    },

    # Edtech/Learning unicorns (5)
    {
        "name": "Byju's",
        "site": "byjus.com",
        "careers_url": "https://www.byjus.com/careers/",
        "verified": True,
    },
    {
        "name": "Unacademy",
        "site": "unacademy.com",
        "careers_url": "https://unacademy.com/careers/",
        "verified": True,
    },
    {
        "name": "Vedantu",
        "site": "vedantu.com",
        "careers_url": "https://www.vedantu.com/careers/",
        "verified": True,
    },
    {
        "name": "Upgrad",
        "site": "upgrad.com",
        "careers_url": "https://www.upgrad.com/careers/",
        "verified": True,
    },
    {
        "name": "PhysicsWallah",
        "site": "physicswallah.com",
        "careers_url": "https://www.physicswallah.com/careers/",
        "verified": True,
    },

    # Healthtech unicorns (4)
    {
        "name": "Practo",
        "site": "practo.com",
        "careers_url": "https://www.practo.com/careers/",
        "verified": True,
    },
    {
        "name": "1mg",
        "site": "1mg.com",
        "careers_url": "https://www.1mg.com/careers/",
        "verified": True,
    },
    {
        "name": "PharmEasy",
        "site": "pharmeasy.in",
        "careers_url": "https://www.pharmeasy.in/careers/",
        "verified": True,
    },
    {
        "name": "Cure.Fit",
        "site": "curefit.com",
        "careers_url": "https://www.curefit.com/careers/",
        "verified": True,
    },

    # Other major Indian tech (3)
    {
        "name": "Dream11",
        "site": "dream11.com",
        "careers_url": "https://www.dream11.com/careers/",
        "verified": True,
    },
    {
        "name": "NoBroker",
        "site": "nobroker.in",
        "careers_url": "https://www.nobroker.in/careers/",
        "verified": True,
    },
    {
        "name": "Policybazaar",
        "site": "policybazaar.com",
        "careers_url": "https://www.policybazaar.com/careers/",
        "verified": True,
    },
]
