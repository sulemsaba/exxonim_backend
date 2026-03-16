from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    BlogAuthor,
    BlogCategory,
    BlogPost,
    Media,
    NavigationItem,
    Page,
    PricingPlan,
    SiteSetting,
    Testimonial,
)

FRONTEND_SRC = ROOT_DIR.parent / "nim" / "src"

ROUTES = {
    "home": "/",
    "about": "/about/",
    "faq": "/faq/",
    "services": "/services/",
    "tracking": "/track-consultation/",
    "resources": "/resources/",
    "career": "/career/",
    "contact": "/contact/",
    "support": "/support/",
    "terms": "/terms/",
    "privacy": "/privacy/",
    "notFound": "/404/",
}

EXTRACT_SCRIPT = r"""
const fs = require("fs");

const args = process.argv.slice(1);
const [filePath, constName, routesJson] = args;
const routes = JSON.parse(routesJson);
const source = fs.readFileSync(filePath, "utf8");

function findConstValue(text, name) {
  const patterns = [
    new RegExp(`export\\s+const\\s+${name}\\s*(?::[^=]+)?=`, "m"),
    new RegExp(`const\\s+${name}\\s*(?::[^=]+)?=`, "m"),
  ];

  let match = null;
  for (const pattern of patterns) {
    match = pattern.exec(text);
    if (match) {
      break;
    }
  }

  if (!match) {
    throw new Error(`Could not find const ${name}`);
  }

  let index = match.index + match[0].length;
  while (index < text.length && /\s/.test(text[index])) {
    index += 1;
  }

  let depth = 0;
  let quote = null;
  let templateDepth = 0;

  for (let i = index; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (quote) {
      if (char === "\\" && quote !== "`") {
        i += 1;
        continue;
      }

      if (quote === "`" && char === "\\") {
        i += 1;
        continue;
      }

      if (quote === "`" && char === "$" && next === "{") {
        templateDepth += 1;
        i += 1;
        continue;
      }

      if (quote === "`" && char === "}" && templateDepth > 0) {
        templateDepth -= 1;
        continue;
      }

      if (char === quote && templateDepth === 0) {
        quote = null;
      }
      continue;
    }

    if (char === "'" || char === '"' || char === "`") {
      quote = char;
      continue;
    }

    if (char === "/" && next === "/") {
      while (i < text.length && text[i] !== "\n") {
        i += 1;
      }
      continue;
    }

    if (char === "/" && next === "*") {
      i += 2;
      while (i < text.length && !(text[i] === "*" && text[i + 1] === "/")) {
        i += 1;
      }
      i += 1;
      continue;
    }

    if (char === "{" || char === "[" || char === "(") {
      depth += 1;
      continue;
    }

    if (char === "}" || char === "]" || char === ")") {
      depth -= 1;
      continue;
    }

    if (char === ";" && depth === 0) {
      return text.slice(index, i).trim().replace(/\s+as const$/, "").trim();
    }
  }

  throw new Error(`Could not parse const ${name}`);
}

const assetImports = {};
const importRegex = /^import\s+([A-Za-z_$][\w$]*)\s+from\s+["']([^"']+)["'];?$/gm;
let importMatch;
while ((importMatch = importRegex.exec(source)) !== null) {
  assetImports[importMatch[1]] = importMatch[2];
}

const valueSource = findConstValue(source, constName);
const argNames = ["routes", ...Object.keys(assetImports)];
const argValues = [routes, ...Object.values(assetImports)];
const evaluator = new Function(...argNames, `return (${valueSource});`);
const value = evaluator(...argValues);
process.stdout.write(JSON.stringify(value));
"""


def extract_const(relative_path: str, const_name: str) -> Any:
    file_path = FRONTEND_SRC / relative_path
    result = subprocess.run(
        ["node", "-e", EXTRACT_SCRIPT, str(file_path), const_name, json.dumps(ROUTES)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def build_blog_content(post: dict[str, Any], article_content: dict[str, Any]) -> dict[str, Any]:
    fallback = {
        "introduction": post["excerpt"],
        "highlights": [
            "Confirm the core facts before the filing or follow-up starts.",
            "Keep supporting records aligned with the exact submission step.",
            "Make the next action visible before the process goes quiet.",
        ],
        "sections": [
            {
                "heading": "Why this matters",
                "paragraphs": [post["excerpt"]],
            },
            {
                "heading": "How Exxonim approaches it",
                "paragraphs": [
                    "Exxonim keeps registration, licensing, and compliance work moving by making the requirement clear, organizing the supporting records, and tying follow-up to the next specific action."
                ],
            },
        ],
    }
    return article_content.get(post["slug"], fallback)


def build_page_rows(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    service_tracking = {
        "eyebrow": "Track your consultation",
        "title": "A clearer view of what happens after you reach out.",
        "description": (
            "Exxonim keeps engagements structured around intake, review, submission, "
            "and follow-up so you are not left guessing where the work stands."
        ),
        "checkpoints": extracted["checkpoints"],
        "case_examples": extracted["caseExamples"],
        "workflow_steps": [
            {
                "title": "1. Intake and scoping",
                "detail": "We clarify the service, requirements, and target outcome before work starts.",
            },
            {
                "title": "2. Preparation and submission",
                "detail": "Documents are checked, gaps are flagged, and the filing pack is prepared.",
            },
            {
                "title": "3. Follow-up and release",
                "detail": "Exxonim tracks the outstanding step until approval, confirmation, or certificate handover.",
            },
        ],
    }

    return [
        {
            "title": "Home",
            "slug": "home",
            "meta_title": "Exxonim | Registration, Compliance, and Licensing Support",
            "meta_description": "Practical support for registrations, filings, permits, and business readiness.",
            "content": {
                "hero": {
                    "eyebrow": "Registration, licensing, and compliance support",
                    "title": "Get help with the filings that keep business moving.",
                    "description": (
                        "Exxonim supports founders, NGOs, and institutions with registration, "
                        "tax setup, licensing, and regulator-facing submissions across Tanzania."
                    ),
                    "cta": {"label": "Request consultation", "href": ROUTES["contact"]},
                    "highlights": extracted["heroHighlights"],
                },
                "provider_section": {
                    "kicker": "Our Clients",
                    "title": "Trusted by Leading Companies",
                    "logos": extracted["providerLogos"],
                },
                "stack_section": {
                    "items": extracted["stackItems"],
                    "default_feature_rows": extracted["defaultFeatureRows"],
                    "feature_visual_content": extracted["featureVisualContentMap"],
                },
                "insights_section": {
                    "title": "Insights and News",
                    "intro": "Sharp guidance for filings, approvals, and growth readiness.",
                    "footer_copy": "Explore more practical articles from the Exxonim resource library.",
                },
            },
        },
        {
            "title": "About Exxonim",
            "slug": "about",
            "meta_title": "About Exxonim",
            "meta_description": "Practical support for registration, compliance, and regulatory follow-through.",
            "content": {
                "hero": {
                    "eyebrow": "About Exxonim",
                    "title": "Practical support for registration, compliance, and regulatory follow-through.",
                    "description": (
                        "Exxonim helps businesses, NGOs, and institutions move through setup, statutory filing, "
                        "licensing, and institutional registration work with clearer preparation and fewer avoidable delays."
                    ),
                },
                "company_profile": {
                    "eyebrow": "What Exxonim is built for",
                    "title": "A company profile grounded in execution, not vague advisory language.",
                    "paragraphs": [
                        "Exxonim exists to help clients handle the work that usually slows progress: preparing correct information, meeting filing requirements, following up after submission, and keeping registration or approval processes moving when details start to drift.",
                        "The focus is practical. We help clients understand what is required, organize what needs to be submitted, and keep the next action visible instead of letting compliance work become an open-ended backlog.",
                    ],
                    "working_style": "Structured preparation, document discipline, and clear next-step follow-through across registration and compliance workflows.",
                },
                "support_profiles": extracted["supportProfiles"],
                "service_scope": extracted["serviceScope"],
                "operating_model": extracted["operatingModel"],
                "client_expectations": extracted["clientExpectations"],
                "cta": {
                    "title": "Start with the next practical step.",
                    "description": (
                        "If you are preparing a registration, cleaning up compliance work, or trying to move a licensing process forward, Exxonim can help you scope what is required and organize the work properly."
                    ),
                    "primary": {"label": "Contact Exxonim", "href": ROUTES["contact"]},
                    "secondary": {"label": "Explore services", "href": ROUTES["services"]},
                },
            },
        },
        {
            "title": "FAQ",
            "slug": "faq",
            "meta_title": "Exxonim FAQ",
            "meta_description": "Common questions before you start.",
            "content": {
                "hero": {
                    "eyebrow": "FAQ",
                    "title": "Common questions before you start.",
                    "description": (
                        "Practical answers around registration, filings, licenses, and the next step after you submit documents to Exxonim."
                    ),
                },
                "items": extracted["faqItems"],
            },
        },
        {
            "title": "Career",
            "slug": "career",
            "meta_title": "Career at Exxonim",
            "meta_description": "Build practical work that helps businesses move forward.",
            "content": {
                "hero": {
                    "eyebrow": "Career",
                    "title": "Build practical work that helps businesses move forward.",
                    "description": (
                        "Exxonim is growing around client service, compliance support, and execution-heavy business operations. "
                        "We look for people who are organized, reliable, and comfortable owning details."
                    ),
                },
                "focus_areas": extracted["careerTracks"],
                "status": {
                    "label": "Open to hearing from strong operators",
                    "description": "Share your background, the type of work you handle well, and the role you think you can grow into.",
                    "primary": {"label": "Send your profile", "href": "mailto:info@exxonim.tz"},
                    "secondary": {"label": "Contact Exxonim", "href": ROUTES["contact"]},
                },
            },
        },
        {
            "title": "Contact",
            "slug": "contact",
            "meta_title": "Contact Exxonim",
            "meta_description": "Reach Exxonim for registration, compliance, or licensing support.",
            "content": {
                "hero": {
                    "eyebrow": "Contact",
                    "title": "Reach Exxonim for registration, compliance, or licensing support.",
                    "description": "Use the contact points below to start a consultation, ask a question, or confirm the next step for an ongoing request.",
                },
                "cards": [
                    {
                        "label": "Call",
                        "value": "+255 794 689 099",
                        "description": "Primary line for new consultations and active follow-up.",
                        "action": {"label": "Call now", "href": "tel:+255794689099"},
                    },
                    {
                        "label": "Email",
                        "value": "info@exxonim.tz",
                        "description": "Send background information, documents, or direct questions.",
                        "action": {"label": "Send email", "href": "mailto:info@exxonim.tz"},
                    },
                    {
                        "label": "Office",
                        "value": "Mbezi Beach B, Africana",
                        "description": "Bagamoyo Road, Block no H, House number 9, Dar es Salaam.",
                        "action": {"label": "WhatsApp", "href": "https://wa.me/255794689099"},
                    },
                ],
            },
        },
        {
            "title": "Services",
            "slug": "services",
            "meta_title": "Exxonim Services",
            "meta_description": "Practical support for registrations, filings, permits, and business readiness.",
            "content": {
                "overview": {
                    "eyebrow": "Exxonim services",
                    "title": "Practical support for registrations, filings, permits, and business readiness.",
                    "description": (
                        "Exxonim works across business setup, tax compliance, licensing, institutional registrations, "
                        "and business support documents. The goal is simple: cleaner preparation, less avoidable back-and-forth, "
                        "and a clearer next step after every submission."
                    ),
                    "panel_title": "Services designed around real filing paths, not generic advice.",
                    "panel_body": (
                        "From BRELA and TRA work to licenses, employer-side registrations, and business plans, Exxonim helps prepare the requirement, coordinate the documents, and keep follow-up moving."
                    ),
                    "service_signals": extracted["serviceSignals"],
                    "service_nav_groups": extracted["serviceNavGroups"],
                    "service_flow": extracted["serviceFlow"],
                    "service_promises": extracted["servicePromises"],
                },
                "catalog": {
                    "eyebrow": "Services",
                    "title": "Practical support across registration, filing, licensing, and business readiness.",
                    "description": "Each service line is structured to reduce back-and-forth, keep documentation organized, and move your application or compliance work toward a clear next step.",
                    "service_groups": extracted["serviceGroups"],
                },
                "tracking_section": service_tracking,
            },
        },
        {
            "title": "Track Consultation",
            "slug": "track-consultation",
            "meta_title": "Track Your Consultation",
            "meta_description": "A clearer view of what happens after you reach out.",
            "content": service_tracking,
        },
        {
            "title": "Resources",
            "slug": "resources",
            "meta_title": "Exxonim Resources",
            "meta_description": "Sharp guidance for filings, approvals, and growth readiness.",
            "content": {
                "hero_title": "Exxonim Blog",
                "top_media": extracted["blogTopMedia"],
                "empty_state": {
                    "title": "Blog posts will appear here.",
                    "description": "Published posts will populate this grid automatically as the library grows.",
                },
            },
        },
        {
            "title": "Support",
            "slug": "support",
            "meta_title": "Exxonim Support",
            "meta_description": "Support channels that keep follow-up clear.",
            "content": {
                "hero": {
                    "eyebrow": "Support",
                    "title": "Support channels that keep follow-up clear.",
                    "description": "Use the right channel for the type of request so registration, filing, and licensing questions reach Exxonim with enough context to move forward.",
                },
                "sections": [
                    {
                        "title": "Best ways to reach Exxonim",
                        "paragraphs": [
                            "For new work, the fastest route is usually a phone call or direct email with a short description of the service you need. For existing work, include the company name, filing type, and the last step already completed."
                        ],
                        "bullets": [
                            "Phone: +255 794 689 099 or +255 685 525 224",
                            "Email: info@exxonim.tz or md@exxonim.tz",
                            "Office: Mbezi Beach B, Africana, Bagamoyo Road, Dar es Salaam",
                        ],
                    },
                    {
                        "title": "What to include in a follow-up",
                        "paragraphs": [
                            "Support requests move faster when Exxonim can immediately identify the matter. Include the client name, the regulator or filing type involved, any reference you were given, and the document or action you need clarified."
                        ],
                        "bullets": [
                            "State whether the request is new work or an ongoing engagement",
                            "Mention the authority, filing, or license involved",
                            "Attach the latest notice, checklist, or submission evidence if relevant",
                        ],
                    },
                    {
                        "title": "What Exxonim can help with",
                        "paragraphs": [
                            "Support covers registration readiness, missing document review, filing sequence questions, licensing clarification, and practical follow-up on ongoing work. Matters that need a formal commercial scope may be moved into a new consultation."
                        ],
                    },
                ],
            },
        },
        {
            "title": "Terms of Use",
            "slug": "terms",
            "meta_title": "Exxonim Terms of Use",
            "meta_description": "Website terms of use.",
            "content": {
                "hero": {
                    "eyebrow": "Terms",
                    "title": "Website terms of use.",
                    "description": "These terms govern how visitors use the Exxonim website and its published materials. They do not replace any separate client engagement terms agreed for paid services.",
                },
                "sections": [
                    {
                        "title": "Using this website",
                        "paragraphs": [
                            "You may use the site to learn about Exxonim services, contact the company, and read published articles. You should not use the site in a way that interferes with its operation or misrepresents the source of its content."
                        ],
                    },
                    {
                        "title": "Informational content only",
                        "paragraphs": [
                            "Articles and website copy are provided for general informational purposes. They are not a substitute for a scoped engagement, document review, or regulator-specific advice on your exact facts."
                        ],
                    },
                    {
                        "title": "Content ownership",
                        "paragraphs": [
                            "Unless otherwise stated, the site design, branding, copy, and published materials belong to Exxonim. You may quote short excerpts with attribution, but you should not republish full materials as your own."
                        ],
                    },
                    {
                        "title": "External links and availability",
                        "paragraphs": [
                            "The site may link to third-party services or references. Exxonim is not responsible for third-party content or availability. The website may be updated, changed, or temporarily unavailable without prior notice."
                        ],
                    },
                ],
            },
        },
        {
            "title": "Privacy Policy",
            "slug": "privacy",
            "meta_title": "Exxonim Privacy Policy",
            "meta_description": "Website privacy policy.",
            "content": {
                "hero": {
                    "eyebrow": "Privacy",
                    "title": "Website privacy policy.",
                    "description": "This page explains the basic information Exxonim may receive through the website and how it is used for contact, support, and business communication.",
                },
                "sections": [
                    {
                        "title": "Information you choose to share",
                        "paragraphs": [
                            "If you contact Exxonim by phone, email, WhatsApp, or another linked channel, Exxonim may receive the information you provide, including your name, company details, contact information, and any documents or context you send."
                        ],
                    },
                    {
                        "title": "How the information is used",
                        "paragraphs": [
                            "That information is used to respond to inquiries, understand the service requested, continue follow-up on ongoing work, and maintain normal business communication around Exxonim services."
                        ],
                    },
                    {
                        "title": "Sharing and retention",
                        "paragraphs": [
                            "Exxonim does not publish private inquiry details on the website. Information may be retained in normal business records where needed to respond to requests, continue support, or maintain a history of communication."
                        ],
                    },
                    {
                        "title": "Questions about privacy",
                        "paragraphs": [
                            "If you want to clarify what information you have shared through the site or how to contact Exxonim about privacy concerns, use the main support channels listed on the contact and support pages."
                        ],
                    },
                ],
            },
        },
        {
            "title": "404",
            "slug": "404",
            "meta_title": "Page Not Found",
            "meta_description": "That page is not available.",
            "content": {
                "hero": {
                    "eyebrow": "404",
                    "title": "That page is not available.",
                    "description": "The address you requested does not match an active Exxonim page. Use one of the main routes below to continue.",
                },
                "sections": [
                    {
                        "title": "Useful destinations",
                        "paragraphs": [
                            "Return to the home page, browse services, or open the resources library to continue from a supported route."
                        ],
                        "bullets": [
                            "Home page and company overview",
                            "Services and registration support",
                            "Resources and practical articles",
                        ],
                    }
                ],
            },
        },
    ]


def build_site_settings(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "key": "brand",
            "value": extracted["brand"],
        },
        {
            "key": "company_info",
            "value": {
                "name": "Exxonim",
                "phones": ["+255 794 689 099", "+255 685 525 224"],
                "emails": ["info@exxonim.tz", "md@exxonim.tz"],
                "address": "Mbezi Beach B, Africana, Bagamoyo Road, Block no H, House number 9, Dar es Salaam",
                "whatsapp": "https://wa.me/255794689099",
            },
        },
        {
            "key": "footer",
            "value": {
                "quick_links": extracted["quickLinks"],
                "other_resources": extracted["otherResources"],
                "tagline": "Where Innovation Meets Efficiency.",
                "primary_cta": {
                    "label": "Track Your Consultation",
                    "href": ROUTES["tracking"],
                },
                "copyright": "© 2026 Exxonim. All rights reserved.",
            },
        },
        {
            "key": "resources_page_media",
            "value": extracted["blogTopMedia"],
        },
    ]


async def seed() -> None:
    extracted = {
        "brand": extract_const("content.ts", "brand"),
        "stackItems": extract_const("content.ts", "stackItems"),
        "blogCategories": extract_const("content.ts", "blogCategories"),
        "blogAuthors": extract_const("content.ts", "blogAuthors"),
        "blogPosts": extract_const("content.ts", "blogPosts"),
        "serviceNavGroups": extract_const("content.ts", "serviceNavGroups"),
        "blogArticleContent": extract_const("blogArticleContent.ts", "blogArticleContent"),
        "supportProfiles": extract_const("pages/AboutPage.tsx", "supportProfiles"),
        "serviceScope": extract_const("pages/AboutPage.tsx", "serviceScope"),
        "operatingModel": extract_const("pages/AboutPage.tsx", "operatingModel"),
        "clientExpectations": extract_const("pages/AboutPage.tsx", "clientExpectations"),
        "faqItems": extract_const("pages/FaqPage.tsx", "faqItems"),
        "careerTracks": extract_const("pages/CareerPage.tsx", "careerTracks"),
        "providerLogos": extract_const("components/ProviderSection.tsx", "providerLogos"),
        "defaultFeatureRows": extract_const("components/StackSection.tsx", "defaultFeatureRows"),
        "featureVisualContentMap": extract_const(
            "components/StackSection.tsx", "featureVisualContentMap"
        ),
        "heroHighlights": extract_const("components/ReferenceHero.tsx", "heroHighlights"),
        "testimonials": extract_const("components/ServicePlansSection.tsx", "TESTIMONIALS"),
        "plans": extract_const("components/ServicePlansSection.tsx", "PLANS"),
        "serviceGroups": extract_const("components/EngineSection.tsx", "serviceGroups"),
        "checkpoints": extract_const("components/ResultsSection.tsx", "checkpoints"),
        "caseExamples": extract_const("components/ResultsSection.tsx", "caseExamples"),
        "serviceSignals": extract_const(
            "components/ServicesOverviewSection.tsx", "serviceSignals"
        ),
        "serviceFlow": extract_const("components/ServicesOverviewSection.tsx", "serviceFlow"),
        "servicePromises": extract_const(
            "components/ServicesOverviewSection.tsx", "servicePromises"
        ),
        "quickLinks": extract_const("components/Footer.tsx", "quickLinks"),
        "otherResources": extract_const("components/Footer.tsx", "otherResources"),
        "blogTopMedia": extract_const("pages/ResourcesPage.tsx", "BLOG_TOP_MEDIA"),
        "desktopLinks": extract_const("components/Navigation.tsx", "desktopLinks"),
        "servicesColumns": extract_const("components/Navigation.tsx", "servicesColumns"),
        "resourcesColumns": extract_const("components/Navigation.tsx", "resourcesColumns"),
    }

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
                        media,
                        site_settings
                    RESTART IDENTITY CASCADE
                    """
                )
            )

            media_lookup: dict[str, Media] = {}

            def ensure_media(url: str | None, alt_text: str | None = None) -> None:
                if not url or url in media_lookup:
                    return
                media = Media(url=url, alt_text=alt_text)
                session.add(media)
                media_lookup[url] = media

            for logo in extracted["providerLogos"]:
                ensure_media(logo.get("src"), logo.get("alt"))

            brand = extracted["brand"]
            ensure_media(brand.get("lightLogoSrc"), f'{brand.get("name", "Exxonim")} light logo')
            ensure_media(brand.get("darkLogoSrc"), f'{brand.get("name", "Exxonim")} dark logo')

            for media_url in [
                extracted["blogTopMedia"].get("hero"),
                extracted["blogTopMedia"].get("banner"),
                *extracted["blogTopMedia"].get("trending", []),
            ]:
                ensure_media(media_url)

            category_lookup: dict[str, BlogCategory] = {}
            for category in extracted["blogCategories"]:
                category_row = BlogCategory(
                    name=category["label"],
                    slug=category["id"],
                    description=category.get("description"),
                )
                session.add(category_row)
                category_lookup[category["id"]] = category_row

            author_lookup: dict[str, BlogAuthor] = {}
            for author in extracted["blogAuthors"]:
                author_row = BlogAuthor(
                    slug=author["id"],
                    name=author["name"],
                    role=author.get("role"),
                    avatar_src=author.get("avatarSrc"),
                )
                session.add(author_row)
                author_lookup[author["id"]] = author_row

            await session.flush()

            for post in extracted["blogPosts"]:
                ensure_media(post.get("coverImageSrc"), post.get("coverAlt"))
                session.add(
                    BlogPost(
                        title=post["title"],
                        slug=post["slug"],
                        excerpt=post.get("excerpt"),
                        content=build_blog_content(post, extracted["blogArticleContent"]),
                        category_id=category_lookup[post["categoryId"]].id,
                        author_id=author_lookup[post["authorId"]].id,
                        featured_image=post.get("coverImageSrc"),
                        cover_alt=post.get("coverAlt"),
                        media_label=post.get("mediaLabel"),
                        featured_slot=post.get("featuredSlot"),
                        featured_on_home=bool(post.get("featuredOnHome")),
                        read_time_minutes=post.get("readTimeMinutes"),
                        related_slugs=post.get("relatedSlugs", []),
                        meta_title=post["title"],
                        meta_description=post.get("excerpt"),
                        published_at=parse_published_at(post.get("publishedAt")),
                        is_published=True,
                    )
                )

            for index, item in enumerate(extracted["desktopLinks"], start=1):
                session.add(
                    NavigationItem(
                        title=item["label"],
                        url=item["href"],
                        kind="primary",
                        order=index,
                        is_active=True,
                    )
                )

            services_root = NavigationItem(
                title="Services",
                url=ROUTES["services"],
                kind="primary",
                order=5,
                is_active=True,
            )
            resources_root = NavigationItem(
                title="Resources",
                url=ROUTES["resources"],
                kind="primary",
                order=6,
                is_active=True,
            )
            session.add_all([services_root, resources_root])
            await session.flush()

            for index, column in enumerate(extracted["servicesColumns"], start=1):
                group = NavigationItem(
                    title=column["title"],
                    url=ROUTES["services"],
                    kind="group",
                    parent_id=services_root.id,
                    order=index,
                    is_active=True,
                )
                session.add(group)
                await session.flush()
                for child_index, item in enumerate(column["items"], start=1):
                    session.add(
                        NavigationItem(
                            title=item["label"],
                            url=item["href"],
                            kind="link",
                            parent_id=group.id,
                            order=child_index,
                            is_active=True,
                        )
                    )

            for index, column in enumerate(extracted["resourcesColumns"], start=1):
                group = NavigationItem(
                    title=column["title"],
                    url=ROUTES["resources"],
                    kind="group",
                    parent_id=resources_root.id,
                    order=index,
                    is_active=True,
                )
                session.add(group)
                await session.flush()
                for child_index, item in enumerate(column["items"], start=1):
                    session.add(
                        NavigationItem(
                            title=item["label"],
                            url=item["href"],
                            kind="link",
                            parent_id=group.id,
                            order=child_index,
                            is_active=True,
                        )
                    )

            for page in build_page_rows(extracted):
                session.add(
                    Page(
                        title=page["title"],
                        slug=page["slug"],
                        content=page["content"],
                        meta_title=page.get("meta_title"),
                        meta_description=page.get("meta_description"),
                        is_published=True,
                    )
                )

            for index, testimonial in enumerate(extracted["testimonials"], start=1):
                session.add(
                    Testimonial(
                        eyebrow=testimonial.get("eyebrow"),
                        headline=testimonial.get("headline"),
                        support=testimonial.get("support"),
                        author=testimonial["name"],
                        author_role=testimonial.get("role"),
                        initials=testimonial.get("initials"),
                        content=testimonial["quote"],
                        sort_order=index,
                        is_active=True,
                    )
                )

            for index, plan in enumerate(extracted["plans"], start=1):
                session.add(
                    PricingPlan(
                        name=plan["name"],
                        badge=plan.get("badge"),
                        description=plan.get("description"),
                        notes=plan.get("notes"),
                        price=None,
                        features=plan.get("features", []),
                        recommended=bool(plan.get("recommended")),
                        sort_order=index,
                        is_active=True,
                    )
                )

            for setting in build_site_settings(extracted):
                session.add(SiteSetting(key=setting["key"], value=setting["value"]))


if __name__ == "__main__":
    asyncio.run(seed())
