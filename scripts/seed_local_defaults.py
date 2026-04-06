from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    BlogAuthor,
    BlogCategory,
    BlogPost,
    NavigationItem,
    Page,
    PricingPlan,
    SiteSetting,
    Testimonial,
)

ROUTES = {
    "home": "/",
    "about": "/about/",
    "faq": "/faq/",
    "services": "/services/",
    "resources": "/resources/",
    "career": "/career/",
    "contact": "/contact/",
    "support": "/support/",
    "terms": "/terms/",
    "privacy": "/privacy/",
    "notFound": "/404/",
}

LOGO_LIGHT = "/assets/exxonim-logo.webp"
LOGO_DARK = "/assets/logo-dark.png"
FAVICON_LIGHT = "/assets/branding/exxonim-favicon-light.png"

PROVIDER_LOGOS = [
    {"alt": "Exxonim", "src": "/assets/clients/exxonim logo.webp"},
    {"alt": "FAMA", "src": "/assets/clients/fama.webp"},
    {"alt": "TRCS", "src": "/assets/clients/trcs.webp"},
    {"alt": "UTEC", "src": "/assets/clients/utec.webp"},
]

HOME_STACK_ITEMS = [
    {
        "title": "Business Setup",
        "subtitle": "Registration before operations start",
        "description": "Company, NGO, and business-name filings prepared with clearer documents and fewer avoidable corrections.",
        "ctaLabel": "Start a registration",
        "ctaHref": ROUTES["contact"],
    },
    {
        "title": "Compliance and Licensing",
        "subtitle": "Tax, permits, and regulator follow-up",
        "description": "TIN applications, licenses, renewals, and statutory follow-up organized into a practical filing sequence.",
        "ctaLabel": "Explore services",
        "ctaHref": ROUTES["services"],
    },
    {
        "title": "Operational Support",
        "subtitle": "Institutional registrations and continuity",
        "description": "Employer-side registrations and ongoing compliance support kept visible so nothing important stalls quietly.",
        "ctaLabel": "Talk to Exxonim",
        "ctaHref": ROUTES["contact"],
    },
]

SITE_SETTINGS = [
    {
        "key": "brand",
        "value": {
            "name": "Exxonim",
            "legalCompanyName": "Exxonim Ltd",
            "companyShortName": "Exxonim",
            "tagline": "Registration, licensing, and compliance support",
            "lightLogoSrc": LOGO_LIGHT,
            "darkLogoSrc": LOGO_DARK,
            "faviconUrl": FAVICON_LIGHT,
            "brandColors": {
                "primary": "#0f5c63",
                "secondary": "#7fbcc1",
            },
        },
    },
    {
        "key": "company_info",
        "value": {
            "name": "Exxonim",
            "legalCompanyName": "Exxonim Ltd",
            "companyShortName": "Exxonim",
            "phones": ["+255 742 000 000"],
            "emails": ["hello@exxonim.tz"],
            "address": "Dar es Salaam, Tanzania",
            "whatsapp": "+255742000000",
        },
    },
    {
        "key": "footer",
        "value": {
            "quick_links": [
                {"label": "Home", "href": ROUTES["home"]},
                {"label": "About", "href": ROUTES["about"]},
                {"label": "Services", "href": ROUTES["services"]},
                {"label": "Resources", "href": ROUTES["resources"]},
            ],
            "other_resources": [
                {"label": "FAQ", "href": ROUTES["faq"]},
                {"label": "Support", "href": ROUTES["support"]},
                {"label": "Terms", "href": ROUTES["terms"]},
                {"label": "Privacy", "href": ROUTES["privacy"]},
            ],
            "tagline": "Practical filing support for registrations, approvals, and compliance work that needs follow-through.",
            "primary_cta": {
                "label": "Contact Exxonim",
                "href": ROUTES["contact"],
            },
            "social_links": [
                {
                    "platform": "linkedin",
                    "label": "LinkedIn",
                    "url": "https://www.linkedin.com/company/exxonim",
                    "isActive": True,
                }
            ],
            "copyright": "Copyright 2026 Exxonim",
        },
    },
    {
        "key": "seo_defaults",
        "value": {
            "siteName": "Exxonim",
            "canonicalBaseUrl": "http://127.0.0.1:5173",
            "defaultMetaTitle": "Exxonim | Registration, Licensing, and Compliance Support",
            "defaultMetaDescription": "Exxonim supports registration, licensing, statutory filing, and business compliance work in Tanzania.",
            "defaultShareImageUrl": LOGO_LIGHT,
            "robotsIndex": True,
            "robotsFollow": True,
        },
    },
]

PAGES = [
    {
        "title": "Home",
        "slug": "home",
        "meta_title": "Exxonim | Registration, Licensing, and Compliance Support",
        "meta_description": "Practical support for registration, licensing, filings, and compliance work in Tanzania.",
        "content": {
            "hero": {
                "eyebrow": "Registration, licensing, and compliance support",
                "title": "Get help with the filings that keep business moving.",
                "description": "Exxonim supports founders, institutions, and growing teams with setup, approvals, and regulator-facing follow-up.",
                "cta": {
                    "label": "Contact Exxonim",
                    "href": ROUTES["contact"],
                },
                "highlights": [
                    {"title": "BRELA", "detail": "Setup support"},
                    {"title": "TRA", "detail": "Tax registration"},
                    {"title": "Licenses", "detail": "Filing follow-up"},
                ],
            },
            "provider_section": {
                "kicker": "Our Clients",
                "title": "Trusted by teams that need clean execution.",
                "logos": PROVIDER_LOGOS,
            },
            "stack_section": {
                "items": HOME_STACK_ITEMS,
                "default_feature_rows": [],
                "feature_visual_content": {},
            },
            "insights_section": {
                "title": "Insights and News",
                "intro": "Practical guidance for registration, licensing, and business compliance.",
                "footer_copy": "Explore more practical articles from the Exxonim resource library.",
            },
        },
    },
    {
        "title": "About Exxonim",
        "slug": "about",
        "meta_title": "About Exxonim",
        "meta_description": "Practical support for registration, compliance, and regulator-facing submissions.",
        "content": {
            "hero": {
                "eyebrow": "About Exxonim",
                "title": "Execution-focused support for registration and compliance work.",
                "description": "We help clients prepare the requirement, organize the paperwork, and keep the next action visible until the process moves.",
            },
            "company_profile": {
                "eyebrow": "What we do",
                "title": "A service model built around follow-through.",
                "paragraphs": [
                    "Exxonim supports business registration, licensing, tax setup, and regulator-facing submissions.",
                    "The work is practical: clarify the requirement, prepare the documents, submit cleanly, and follow up until there is an answer.",
                ],
                "working_style_label": "Working style",
                "working_style": "Clear preparation, orderly filings, and visible next steps.",
            },
            "support_profiles_section": {
                "title": "Who we support",
                "description": "Teams that need registration and compliance work to move with less confusion.",
            },
            "support_profiles": [
                {
                    "title": "Founders and new businesses",
                    "description": "Setup, statutory registration, and early compliance support.",
                },
                {
                    "title": "Growing companies",
                    "description": "Licenses, renewals, tax-facing filings, and employer-side registrations.",
                },
                {
                    "title": "Institutions and NGOs",
                    "description": "Structured submissions, regulator follow-up, and documentation support.",
                },
            ],
            "service_scope_section": {
                "title": "Service scope",
                "description": "Execution support across setup, approvals, and ongoing compliance.",
            },
            "service_scope": [
                {
                    "title": "Registration and setup",
                    "description": "Business names, companies, NGOs, and related setup steps.",
                },
                {
                    "title": "Tax and licensing",
                    "description": "TIN, VAT, business licenses, and authority-facing follow-up.",
                },
                {
                    "title": "Institutional compliance",
                    "description": "Employer-side and institutional registration requirements kept current.",
                },
            ],
            "operating_model_section": {
                "title": "How the work moves",
                "description": "A simple process that keeps the next action visible.",
            },
            "operating_model": [
                {
                    "step": "01",
                    "title": "Clarify the requirement",
                    "description": "Define the filing path, supporting records, and timing constraints.",
                },
                {
                    "step": "02",
                    "title": "Prepare and submit",
                    "description": "Organize clean submission materials and complete the filing sequence.",
                },
                {
                    "step": "03",
                    "title": "Track and follow up",
                    "description": "Keep the response path active until approval, correction, or completion.",
                },
            ],
            "client_expectations_section": {
                "title": "What clients can expect",
                "description": "Clear communication around requirements, progress, and next steps.",
            },
            "client_expectations": [
                "Straightforward guidance on what is required.",
                "Preparation focused on avoiding preventable delays.",
                "Visible follow-up after submission.",
            ],
            "cta": {
                "title": "Need support with an active filing or setup?",
                "description": "We can help scope the requirement and organize the next move.",
                "primary": {
                    "label": "Contact Exxonim",
                    "href": ROUTES["contact"],
                },
                "secondary": {
                    "label": "View services",
                    "href": ROUTES["services"],
                },
            },
        },
    },
    {
        "title": "FAQ",
        "slug": "faq",
        "meta_title": "Exxonim FAQ",
        "meta_description": "Answers to common registration, filing, licensing, and support questions.",
        "content": {
            "hero": {
                "eyebrow": "Frequently asked questions",
                "title": "Practical answers before you start the filing.",
                "description": "A few of the questions clients usually ask before registration, licensing, or regulator follow-up begins.",
            },
            "items": [
                {
                    "question": "What kind of work does Exxonim handle?",
                    "answer": "Registration, tax setup, licensing, employer-side compliance, and regulator-facing follow-up.",
                },
                {
                    "question": "Can you help if a process has already started?",
                    "answer": "Yes. We can step in to review what has been filed, identify what is missing, and outline the next action.",
                },
                {
                    "question": "Do I need all documents ready before contacting you?",
                    "answer": "No. It helps to share what you already have, and we can help identify the missing pieces.",
                },
                {
                    "question": "Do you support businesses outside Dar es Salaam?",
                    "answer": "Yes. Support can still be coordinated remotely depending on the filing and regulator involved.",
                },
            ],
        },
    },
    {
        "title": "Career",
        "slug": "career",
        "meta_title": "Career at Exxonim",
        "meta_description": "Explore local roles across client support, compliance operations, and execution work.",
        "content": {
            "hero": {
                "eyebrow": "Career",
                "title": "Join work that rewards clarity and follow-through.",
                "description": "We are interested in people who can keep registration and compliance work organized from intake to completion.",
            },
            "focus_areas": [
                "Client-facing coordination",
                "Regulatory and filing operations",
                "Business support workflows",
                "Documentation and follow-up tracking",
            ],
            "status": {
                "label": "Local hiring status",
                "description": "Roles are shared here when there is an active opening. You can still reach out with a relevant profile.",
                "primary": {
                    "label": "Contact Exxonim",
                    "href": ROUTES["contact"],
                },
                "secondary": {
                    "label": "View resources",
                    "href": ROUTES["resources"],
                },
            },
        },
    },
    {
        "title": "Contact",
        "slug": "contact",
        "meta_title": "Contact Exxonim",
        "meta_description": "Reach Exxonim for registration, licensing, and compliance support.",
        "content": {
            "hero": {
                "eyebrow": "Contact",
                "title": "Reach Exxonim for registration and compliance support.",
                "description": "Use the channel that best matches the request so the filing can move with enough context from the start.",
            },
            "cards": [
                {
                    "label": "Phone",
                    "value": "+255 742 000 000",
                    "description": "Best for active matters that need quick clarification.",
                    "action": {
                        "label": "Call now",
                        "href": "tel:+255742000000",
                    },
                },
                {
                    "label": "Email",
                    "value": "hello@exxonim.tz",
                    "description": "Useful for document-heavy questions and formal follow-up.",
                    "action": {
                        "label": "Send email",
                        "href": "mailto:hello@exxonim.tz",
                    },
                },
                {
                    "label": "WhatsApp",
                    "value": "+255 742 000 000",
                    "description": "Fast updates for ongoing registration and licensing matters.",
                    "action": {
                        "label": "Open WhatsApp",
                        "href": "https://wa.me/255742000000",
                    },
                },
            ],
        },
    },
    {
        "title": "Services",
        "slug": "services",
        "meta_title": "Exxonim Services",
        "meta_description": "Registration, tax, licensing, and institutional support services.",
        "content": {
            "overview": {
                "eyebrow": "Services",
                "title": "Support that keeps filings and approvals moving.",
                "description": "Exxonim helps businesses and institutions prepare submissions, organize supporting records, and follow up after filing.",
                "panel_title": "What clients usually need",
                "panel_body": "Clarity on requirements, cleaner documentation, and visible next steps after submission.",
                "service_signals": [
                    {
                        "value": "01",
                        "label": "Registration",
                        "detail": "Business, company, NGO, and trademark setup work.",
                    },
                    {
                        "value": "02",
                        "label": "Licensing",
                        "detail": "Applications, renewals, and approval follow-up.",
                    },
                    {
                        "value": "03",
                        "label": "Compliance",
                        "detail": "Tax-facing and employer-side registration support.",
                    },
                ],
                "service_nav_groups": [
                    {
                        "title": "Setup and registration",
                        "summary": "Start the legal structure cleanly.",
                        "href": ROUTES["contact"],
                        "items": [
                            "Company registration",
                            "Business name registration",
                            "NGO registration",
                        ],
                    },
                    {
                        "title": "Tax and licenses",
                        "summary": "Prepare filings and regulator follow-up.",
                        "href": ROUTES["contact"],
                        "items": [
                            "TIN application",
                            "VAT and tax registration",
                            "Business license applications",
                        ],
                    },
                    {
                        "title": "Institutional support",
                        "summary": "Keep employer-side requirements visible.",
                        "href": ROUTES["contact"],
                        "items": [
                            "NSSF and WCF",
                            "OSHA support",
                            "Regulator coordination",
                        ],
                    },
                ],
                "service_flow": [
                    {
                        "step": "Step 1",
                        "title": "Define the filing path",
                        "detail": "Clarify the requirement and supporting records.",
                    },
                    {
                        "step": "Step 2",
                        "title": "Prepare the submission",
                        "detail": "Organize the documents and complete the filing sequence.",
                    },
                    {
                        "step": "Step 3",
                        "title": "Track the next action",
                        "detail": "Follow up until there is an answer, revision, or approval.",
                    },
                ],
                "service_promises": [
                    "Clearer preparation before the filing starts.",
                    "Less confusion around document requirements.",
                    "Visible next steps after submission.",
                ],
            },
            "catalog": {
                "eyebrow": "Service catalog",
                "title": "Where we usually help most.",
                "description": "A few of the recurring service areas clients bring to Exxonim.",
                "service_groups": [
                    {
                        "title": "Registration and setup",
                        "description": "Foundational work before operations begin.",
                        "services": [
                            {
                                "id": "company-registration",
                                "label": "Company Registration",
                                "detail": "Preparation and filing support for new company setup.",
                            },
                            {
                                "id": "business-name",
                                "label": "Business Name Registration",
                                "detail": "Name reservation and related setup work.",
                            },
                        ],
                    },
                    {
                        "title": "Tax and licensing",
                        "description": "Approvals and regulator-facing submissions.",
                        "services": [
                            {
                                "id": "tin-application",
                                "label": "TIN Application",
                                "detail": "Tax registration support for new and active entities.",
                            },
                            {
                                "id": "business-license",
                                "label": "Business License Applications",
                                "detail": "Applications, renewals, and supporting documentation.",
                            },
                        ],
                    },
                ],
            },
            "tracking_section": {
                "eyebrow": "Tracking",
                "title": "Keep follow-up visible after submission.",
                "description": "A simple structure for monitoring what is done, what is pending, and what needs action next.",
                "checkpoints": [
                    {
                        "title": "Submission complete",
                        "detail": "The filing pack is accepted and logged.",
                        "status": "Complete",
                    },
                    {
                        "title": "Authority review",
                        "detail": "The request is under active review.",
                        "status": "In progress",
                    },
                ],
                "case_examples": [
                    {
                        "title": "Registration follow-up",
                        "detail": "Track document corrections without losing the submission history.",
                    }
                ],
                "workflow_steps": [
                    {
                        "title": "Prepare",
                        "detail": "Clarify requirement and collect evidence.",
                    },
                    {
                        "title": "Submit",
                        "detail": "File cleanly and store references.",
                    },
                    {
                        "title": "Follow up",
                        "detail": "Keep the next action visible until completion.",
                    },
                ],
            },
        },
    },
    {
        "title": "Resources",
        "slug": "resources",
        "meta_title": "Exxonim Resources",
        "meta_description": "Guides and practical notes on registration, licensing, and compliance work.",
        "content": {
            "hero_title": "Exxonim Blog",
            "trending_label": "Trending articles",
            "top_media": {
                "hero": "/assets/clients/jkm.webp",
                "banner": "/assets/clients/levo.webp",
                "trending": [
                    "/assets/clients/utec.webp",
                    "/assets/clients/get.webp",
                    "/assets/clients/trcs.webp",
                ],
            },
            "article_sidebar": {
                "title": "Need support with a live filing?",
                "description": "Use the contact route if you need help turning an article into the next practical action.",
                "primary_cta": {
                    "label": "Contact Exxonim",
                    "href": ROUTES["contact"],
                },
            },
            "empty_state": {
                "title": "More articles are on the way.",
                "description": "Use the FAQ or contact route if you need help with a live matter right now.",
            },
        },
    },
    {
        "title": "Support",
        "slug": "support",
        "meta_title": "Exxonim Support",
        "meta_description": "How to reach Exxonim and what to include in a support request.",
        "content": {
            "hero": {
                "eyebrow": "Support",
                "title": "Use the right channel for the request.",
                "description": "Support moves faster when the matter, regulator, and next action are clear from the start.",
            },
            "sections": [
                {
                    "title": "What to include",
                    "paragraphs": [
                        "Share the client name, the regulator or filing involved, and the specific action you need clarified.",
                    ],
                    "bullets": [
                        "Reference number if one exists",
                        "Documents already submitted",
                        "Current blocker or next action",
                    ],
                },
                {
                    "title": "Best contact routes",
                    "paragraphs": [
                        "Use phone or WhatsApp for active follow-up, and email when documents need to be reviewed together.",
                    ],
                },
            ],
            "next_step": {
                "title": "Need direct help now?",
                "description": "Use the main contact route if the matter is active.",
                "primary_action": {
                    "label": "Contact Exxonim",
                    "href": ROUTES["contact"],
                },
                "secondary_action": {
                    "label": "Read the FAQ",
                    "href": ROUTES["faq"],
                },
            },
        },
    },
    {
        "title": "Terms",
        "slug": "terms",
        "meta_title": "Exxonim Terms of Use",
        "meta_description": "Basic terms for using the Exxonim website and published materials.",
        "content": {
            "hero": {
                "eyebrow": "Terms",
                "title": "Basic terms for using this site.",
                "description": "These terms cover the website itself and do not replace any separate client engagement terms.",
            },
            "sections": [
                {
                    "title": "Use of the website",
                    "paragraphs": [
                        "You may use the site to learn about Exxonim services, contact the company, and review published materials.",
                    ],
                },
                {
                    "title": "Content ownership",
                    "paragraphs": [
                        "Unless otherwise stated, the site design, branding, and published copy remain the property of Exxonim.",
                    ],
                },
            ],
        },
    },
    {
        "title": "Privacy",
        "slug": "privacy",
        "meta_title": "Exxonim Privacy Policy",
        "meta_description": "How Exxonim handles information shared through the website.",
        "content": {
            "hero": {
                "eyebrow": "Privacy",
                "title": "How information shared through the site is used.",
                "description": "This page explains the basic information Exxonim may receive and how it is used for communication and support.",
            },
            "sections": [
                {
                    "title": "Information received",
                    "paragraphs": [
                        "If you contact Exxonim, we may receive your name, company details, contact information, and any documents you provide.",
                    ],
                },
                {
                    "title": "How it is used",
                    "paragraphs": [
                        "That information is used to respond to inquiries, understand the request, and continue normal business follow-up.",
                    ],
                },
            ],
        },
    },
    {
        "title": "Not Found",
        "slug": "404",
        "meta_title": "Page not found | Exxonim",
        "meta_description": "The page you requested could not be found.",
        "content": {
            "hero": {
                "eyebrow": "Page not found",
                "title": "The address you requested is not active.",
                "description": "Use one of the main routes below to continue.",
            },
            "sections": [
                {
                    "title": "Try one of these routes",
                    "paragraphs": [
                        "Start again from the homepage or jump to services, resources, or contact.",
                    ],
                    "bullets": [
                        "Homepage",
                        "Services",
                        "Resources",
                        "Contact",
                    ],
                }
            ],
            "next_step": {
                "title": "Continue from a live section",
                "description": "Use the main site routes to get back on track.",
                "primary_action": {
                    "label": "Go home",
                    "href": ROUTES["home"],
                },
                "secondary_action": {
                    "label": "Contact Exxonim",
                    "href": ROUTES["contact"],
                },
            },
        },
    },
]

BLOG_CATEGORIES = [
    {
        "name": "Guides",
        "slug": "guides",
        "description": "Practical filing and compliance guides.",
    },
    {
        "name": "Operations",
        "slug": "operations",
        "description": "Notes on follow-up, documentation, and workflow.",
    },
]

BLOG_AUTHORS = [
    {
        "name": "Exxonim Editorial",
        "slug": "exxonim-editorial",
        "role": "Operations Desk",
        "avatar_src": LOGO_LIGHT,
    }
]


def blog_body(title: str, excerpt: str, action_label: str) -> dict[str, object]:
    return {
        "introduction": excerpt,
        "highlights": [
            "Clarify the exact requirement before filing starts.",
            "Keep supporting records aligned with the current submission step.",
            f"Define the next action once {action_label} is submitted.",
        ],
        "sections": [
            {
                "heading": "Why this matters",
                "paragraphs": [
                    excerpt,
                    "Most delays come from unclear requirements, missing support records, or weak follow-up after submission.",
                ],
            },
            {
                "heading": "How to keep the process moving",
                "paragraphs": [
                    "Start with the regulator's actual requirement, prepare a clean submission pack, and keep one visible owner for the next action.",
                    f"That makes it easier to respond quickly when {action_label} needs revision, clarification, or confirmation.",
                ],
            },
            {
                "heading": "What Exxonim usually supports",
                "paragraphs": [
                    "We help organize the requirement, align the supporting documents, and keep the submission path visible until there is an outcome.",
                ],
            },
        ],
    }


now = datetime.now(timezone.utc)
BLOG_POSTS = [
    {
        "title": "How to prepare for company registration without avoidable delays",
        "slug": "company-registration-checklist",
        "excerpt": "A short checklist for preparing company registration documents before the filing starts.",
        "category_slug": "guides",
        "author_slug": "exxonim-editorial",
        "featured_image": "/assets/clients/jotofa.webp",
        "cover_alt": "Company registration checklist",
        "media_label": "Guide",
        "featured_slot": "hero",
        "featured_on_home": True,
        "read_time_minutes": 5,
        "related_slugs": ["tin-application-preparation", "licensing-follow-up-rhythm"],
        "published_at": now - timedelta(days=7),
        "content": blog_body(
            "How to prepare for company registration without avoidable delays",
            "A short checklist for preparing company registration documents before the filing starts.",
            "the registration pack",
        ),
    },
    {
        "title": "What to prepare before a TIN application",
        "slug": "tin-application-preparation",
        "excerpt": "The documents and practical checks that help a TIN application move with less back-and-forth.",
        "category_slug": "guides",
        "author_slug": "exxonim-editorial",
        "featured_image": "/assets/clients/get.webp",
        "cover_alt": "TIN application preparation",
        "media_label": "Tax guide",
        "featured_slot": "popular",
        "featured_on_home": True,
        "read_time_minutes": 4,
        "related_slugs": ["company-registration-checklist", "licensing-follow-up-rhythm"],
        "published_at": now - timedelta(days=5),
        "content": blog_body(
            "What to prepare before a TIN application",
            "The documents and practical checks that help a TIN application move with less back-and-forth.",
            "the TIN application",
        ),
    },
    {
        "title": "A better follow-up rhythm for licensing applications",
        "slug": "licensing-follow-up-rhythm",
        "excerpt": "How to track next actions after submission so license applications do not go quiet.",
        "category_slug": "operations",
        "author_slug": "exxonim-editorial",
        "featured_image": "/assets/clients/trcs.webp",
        "cover_alt": "Licensing follow-up rhythm",
        "media_label": "Operations note",
        "featured_slot": "editors-pick",
        "featured_on_home": False,
        "read_time_minutes": 6,
        "related_slugs": ["tin-application-preparation", "company-registration-checklist"],
        "published_at": now - timedelta(days=3),
        "content": blog_body(
            "A better follow-up rhythm for licensing applications",
            "How to track next actions after submission so license applications do not go quiet.",
            "the licensing request",
        ),
    },
]

TESTIMONIALS = [
    {
        "eyebrow": "Client feedback",
        "headline": "Clear support from start to submission.",
        "support": "The filing path and the next step stayed clear throughout the process.",
        "author": "A. Michael",
        "author_role": "Founder",
        "initials": "AM",
        "content": "Exxonim helped us move through the registration work with less confusion and better follow-up after submission.",
        "sort_order": 1,
    },
    {
        "eyebrow": "Client feedback",
        "headline": "Fast responses on an active licensing matter.",
        "support": "We needed practical follow-up, not vague advice.",
        "author": "R. Daniel",
        "author_role": "Operations Lead",
        "initials": "RD",
        "content": "The support was practical. We always knew what had been filed, what was pending, and what came next.",
        "sort_order": 2,
    },
    {
        "eyebrow": "Client feedback",
        "headline": "A cleaner process for compliance follow-up.",
        "support": "The document trail and next actions were easier to manage.",
        "author": "S. Rehema",
        "author_role": "Administrator",
        "initials": "SR",
        "content": "Exxonim made a messy compliance process easier to understand and easier to keep moving.",
        "sort_order": 3,
    },
]

PRICING_PLANS = [
    {
        "name": "Starter Support",
        "badge": "For new filings",
        "description": "Good for a focused registration or single regulator-facing request.",
        "notes": "Best when the scope is clear and the supporting records are mostly ready.",
        "recommended": False,
        "sort_order": 1,
        "features": [
            {"label": "Requirement review", "included": True},
            {"label": "Document checklist", "included": True},
            {"label": "Follow-up support", "included": False},
        ],
    },
    {
        "name": "Active Filing Support",
        "badge": "Recommended",
        "description": "For matters that need preparation, submission support, and visible follow-up.",
        "notes": "A practical fit for licensing, tax setup, and regulator-facing processes.",
        "recommended": True,
        "sort_order": 2,
        "features": [
            {"label": "Requirement review", "included": True},
            {"label": "Submission preparation", "included": True},
            {"label": "Follow-up support", "included": True},
        ],
    },
    {
        "name": "Ongoing Compliance Support",
        "badge": "For teams",
        "description": "For recurring filings, institutional registrations, and ongoing coordination.",
        "notes": "Useful when there are multiple compliance touchpoints to manage over time.",
        "recommended": False,
        "sort_order": 3,
        "features": [
            {"label": "Recurring filing support", "included": True},
            {"label": "Institutional coordination", "included": True},
            {"label": "Priority follow-up", "included": True},
        ],
    },
]


async def seed_local_defaults() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    TRUNCATE TABLE
                        blog_posts,
                        blog_authors,
                        blog_categories,
                        navigation_items,
                        pages,
                        testimonials,
                        pricing_plans,
                        site_settings
                    RESTART IDENTITY CASCADE
                    """
                )
            )

            for setting in SITE_SETTINGS:
                session.add(SiteSetting(key=setting["key"], value=setting["value"]))

            top_level_items = [
                ("Home", ROUTES["home"], 1),
                ("About", ROUTES["about"], 2),
                ("Services", ROUTES["services"], 3),
                ("Resources", ROUTES["resources"], 4),
                ("FAQ", ROUTES["faq"], 5),
                ("Contact", ROUTES["contact"], 6),
            ]

            top_level_lookup: dict[str, NavigationItem] = {}
            for title, url, order in top_level_items:
                item = NavigationItem(
                    title=title,
                    url=url,
                    kind="primary",
                    order=order,
                    is_active=True,
                )
                session.add(item)
                top_level_lookup[title] = item

            await session.flush()

            services_root = top_level_lookup["Services"]
            resources_root = top_level_lookup["Resources"]

            services_groups = [
                (
                    "Business Setup",
                    [
                        ("Company Registration", ROUTES["services"]),
                        ("TIN Application", ROUTES["services"]),
                        ("Business License Applications", ROUTES["services"]),
                    ],
                ),
                (
                    "Institutional Support",
                    [
                        ("NSSF and WCF", ROUTES["services"]),
                        ("OSHA Support", ROUTES["services"]),
                    ],
                ),
            ]

            for group_order, (title, children) in enumerate(services_groups, start=1):
                group = NavigationItem(
                    title=title,
                    url=ROUTES["services"],
                    kind="group",
                    parent_id=services_root.id,
                    order=group_order,
                    is_active=True,
                )
                session.add(group)
                await session.flush()

                for item_order, (label, href) in enumerate(children, start=1):
                    session.add(
                        NavigationItem(
                            title=label,
                            url=href,
                            kind="link",
                            parent_id=group.id,
                            order=item_order,
                            is_active=True,
                        )
                    )

            resources_groups = [
                (
                    "Knowledge Base",
                    [
                        ("Blog", ROUTES["resources"]),
                        ("FAQ", ROUTES["faq"]),
                    ],
                ),
                (
                    "Get Help",
                    [
                        ("Support", ROUTES["support"]),
                        ("Contact", ROUTES["contact"]),
                    ],
                ),
            ]

            for group_order, (title, children) in enumerate(resources_groups, start=1):
                group = NavigationItem(
                    title=title,
                    url=ROUTES["resources"],
                    kind="group",
                    parent_id=resources_root.id,
                    order=group_order,
                    is_active=True,
                )
                session.add(group)
                await session.flush()

                for item_order, (label, href) in enumerate(children, start=1):
                    session.add(
                        NavigationItem(
                            title=label,
                            url=href,
                            kind="link",
                            parent_id=group.id,
                            order=item_order,
                            is_active=True,
                        )
                    )

            for page in PAGES:
                session.add(
                    Page(
                        title=page["title"],
                        slug=page["slug"],
                        content=page["content"],
                        meta_title=page["meta_title"],
                        meta_description=page["meta_description"],
                        is_published=True,
                    )
                )

            category_lookup: dict[str, BlogCategory] = {}
            for category in BLOG_CATEGORIES:
                row = BlogCategory(
                    name=category["name"],
                    slug=category["slug"],
                    description=category["description"],
                )
                session.add(row)
                category_lookup[category["slug"]] = row

            author_lookup: dict[str, BlogAuthor] = {}
            for author in BLOG_AUTHORS:
                row = BlogAuthor(
                    name=author["name"],
                    slug=author["slug"],
                    role=author["role"],
                    avatar_src=author["avatar_src"],
                )
                session.add(row)
                author_lookup[author["slug"]] = row

            await session.flush()

            for post in BLOG_POSTS:
                session.add(
                    BlogPost(
                        title=post["title"],
                        slug=post["slug"],
                        excerpt=post["excerpt"],
                        content=post["content"],
                        category_id=category_lookup[post["category_slug"]].id,
                        author_id=author_lookup[post["author_slug"]].id,
                        featured_image=post["featured_image"],
                        cover_alt=post["cover_alt"],
                        media_label=post["media_label"],
                        featured_slot=post["featured_slot"],
                        featured_on_home=post["featured_on_home"],
                        read_time_minutes=post["read_time_minutes"],
                        related_slugs=post["related_slugs"],
                        meta_title=post["title"],
                        meta_description=post["excerpt"],
                        published_at=post["published_at"],
                        is_published=True,
                    )
                )

            for testimonial in TESTIMONIALS:
                session.add(
                    Testimonial(
                        eyebrow=testimonial["eyebrow"],
                        headline=testimonial["headline"],
                        support=testimonial["support"],
                        author=testimonial["author"],
                        author_role=testimonial["author_role"],
                        initials=testimonial["initials"],
                        content=testimonial["content"],
                        sort_order=testimonial["sort_order"],
                        is_active=True,
                    )
                )

            for plan in PRICING_PLANS:
                session.add(
                    PricingPlan(
                        name=plan["name"],
                        badge=plan["badge"],
                        description=plan["description"],
                        notes=plan["notes"],
                        features=plan["features"],
                        recommended=plan["recommended"],
                        sort_order=plan["sort_order"],
                        is_active=True,
                    )
                )

    print("Seeded local public-site defaults into the current database.")


if __name__ == "__main__":
    asyncio.run(seed_local_defaults())
