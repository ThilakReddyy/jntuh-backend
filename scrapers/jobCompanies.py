"""Canonical company metadata used by the India early-career job pipeline.

The registry intentionally separates company classification from retrieval.  A
company can change applicant-tracking systems without changing whether it is a
product or services company, and aggregator results still receive the same
canonical classification.
"""

from dataclasses import dataclass


PRODUCT = "PRODUCT"
SERVICE = "SERVICE"
OTHER = "OTHER"


@dataclass(frozen=True)
class CompanyTarget:
    name: str
    company_type: str
    aliases: tuple[str, ...] = ()
    ats_provider: str | None = None
    ats_key: str | None = None


# Public ATS keys are only set when the company exposes a public board through
# that provider.  Companies without one remain in the registry so jobs found by
# supplemental feeds are still normalized and classified correctly.
TARGET_COMPANIES: tuple[CompanyTarget, ...] = (
    CompanyTarget("Amazon", PRODUCT, ("Amazon Web Services", "AWS")),
    CompanyTarget("Google", PRODUCT, ("Google India", "Alphabet")),
    CompanyTarget("Meta", PRODUCT, ("Facebook", "Instagram", "WhatsApp")),
    CompanyTarget("Microsoft", PRODUCT, ("Microsoft India", "LinkedIn")),
    CompanyTarget("Apple", PRODUCT),
    CompanyTarget("Adobe", PRODUCT),
    CompanyTarget("Salesforce", PRODUCT),
    CompanyTarget("Oracle", PRODUCT),
    CompanyTarget("SAP", PRODUCT, ("SAP Labs",)),
    CompanyTarget("Atlassian", PRODUCT),
    CompanyTarget("Uber", PRODUCT),
    CompanyTarget("Flipkart", PRODUCT),
    CompanyTarget("Walmart Global Tech", PRODUCT, ("Walmart Labs", "Walmart")),
    CompanyTarget("PhonePe", PRODUCT),
    CompanyTarget("Razorpay", PRODUCT),
    CompanyTarget("Paytm", PRODUCT, ("One97 Communications",)),
    CompanyTarget("Zomato", PRODUCT, ("Blinkit",)),
    CompanyTarget("Swiggy", PRODUCT),
    CompanyTarget("Zerodha", PRODUCT),
    CompanyTarget("CRED", PRODUCT),
    CompanyTarget("Meesho", PRODUCT),
    CompanyTarget("Groww", PRODUCT),
    CompanyTarget("Freshworks", PRODUCT),
    CompanyTarget("Zoho", PRODUCT, ("Zoho Corporation",)),
    CompanyTarget("BrowserStack", PRODUCT),
    CompanyTarget("Postman", PRODUCT),
    CompanyTarget("Dream11", PRODUCT, ("Dream Sports",)),
    CompanyTarget("InMobi", PRODUCT, ("Glance",)),
    CompanyTarget("OYO", PRODUCT, ("OYO Rooms",)),
    CompanyTarget("Ola", PRODUCT, ("Ola Electric", "ANI Technologies")),
    CompanyTarget("Myntra", PRODUCT),
    CompanyTarget("MakeMyTrip", PRODUCT, ("Goibibo",)),
    CompanyTarget("Practo", PRODUCT),
    CompanyTarget("Chargebee", PRODUCT),
    CompanyTarget("Juspay", PRODUCT),
    CompanyTarget("NVIDIA", PRODUCT),
    CompanyTarget("Intel", PRODUCT),
    CompanyTarget("AMD", PRODUCT, ("Advanced Micro Devices",)),
    CompanyTarget("Qualcomm", PRODUCT),
    CompanyTarget("Cisco", PRODUCT),
    CompanyTarget("ServiceNow", PRODUCT),
    CompanyTarget("Stripe", PRODUCT),
    CompanyTarget("Coinbase", PRODUCT),
    CompanyTarget("Datadog", PRODUCT),
    CompanyTarget("Twilio", PRODUCT),
    CompanyTarget("Airbnb", PRODUCT),
    CompanyTarget("Netflix", PRODUCT),
    CompanyTarget("Spotify", PRODUCT),
    CompanyTarget("Nirmata", PRODUCT),
    CompanyTarget("CloudSEK", PRODUCT),
    CompanyTarget("Karya", PRODUCT),
    CompanyTarget("Stable Money", PRODUCT),
    CompanyTarget("Glance", PRODUCT),
    CompanyTarget("Wabtec", PRODUCT),
    CompanyTarget("Bosch", PRODUCT, ("Bosch Group", "Bosch Rexroth")),
    CompanyTarget("Renesas Electronics", PRODUCT, ("Renesas",)),
    CompanyTarget("Continental", PRODUCT),
    CompanyTarget("Experian", PRODUCT),
    CompanyTarget("Brainwonders", SERVICE),
    CompanyTarget("Ramboll", SERVICE),
    CompanyTarget("AECOM", SERVICE),
    CompanyTarget("Turner & Townsend", SERVICE, ("Turner and Townsend",)),
    CompanyTarget("Nagarro", SERVICE),
    CompanyTarget("Sutherland", SERVICE, ("Sutherland Global Services",)),
    CompanyTarget("TCS", SERVICE, ("Tata Consultancy Services",)),
    CompanyTarget("Infosys", SERVICE),
    CompanyTarget("Wipro", SERVICE),
    CompanyTarget("HCLTech", SERVICE, ("HCL Technologies", "HCL")),
    CompanyTarget("Tech Mahindra", SERVICE),
    CompanyTarget("Cognizant", SERVICE, ("Cognizant Technology Solutions",)),
    CompanyTarget("Accenture", SERVICE),
    CompanyTarget("Capgemini", SERVICE),
    CompanyTarget("LTIMindtree", SERVICE, ("LTI Mindtree", "Larsen & Toubro Infotech")),
    CompanyTarget("Mphasis", SERVICE),
    CompanyTarget("Hexaware", SERVICE),
    CompanyTarget("Persistent Systems", SERVICE, ("Persistent",)),
    CompanyTarget("Coforge", SERVICE, ("NIIT Technologies",)),
    CompanyTarget("IBM Consulting", SERVICE, ("IBM India", "IBM")),
    CompanyTarget("Deloitte", SERVICE),
    CompanyTarget("EY", SERVICE, ("Ernst & Young",)),
    CompanyTarget("PwC", SERVICE, ("PricewaterhouseCoopers",)),
    CompanyTarget("KPMG", SERVICE),
    CompanyTarget("NTT DATA", SERVICE, ("NTT Data Services",)),
)


def _company_token(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


COMPANY_ALIASES: dict[str, CompanyTarget] = {
    _company_token(alias): company
    for company in TARGET_COMPANIES
    for alias in (company.name, *company.aliases)
}


def classify_company(company_name: str) -> tuple[str, str]:
    """Return ``(canonical name, type)`` using explicit aliases only."""

    normalized = _company_token(company_name)
    direct = COMPANY_ALIASES.get(normalized)
    if direct:
        return direct.name, direct.company_type

    # ATS feeds sometimes append a legal suffix or business unit.  Matching a
    # sufficiently distinctive alias as a whole normalized segment handles
    # values such as "Google India Pvt Ltd" without fuzzy false positives.
    for alias, target in COMPANY_ALIASES.items():
        if len(alias) >= 5 and alias in normalized:
            return target.name, target.company_type
    return company_name.strip(), OTHER
