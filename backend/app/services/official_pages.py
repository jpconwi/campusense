"""
services/official_pages.py - the official NEMSU website pages the chatbot should know.

One URL per line. To teach the AI a new page, add its link here and run a sync
(or redeploy). Links that differ only by "#section" count as one page.
"""

OFFICIAL_PAGES = [
    # about / leadership
    "https://nemsu.edu.ph/about/board-of-regents",
    "https://nemsu.edu.ph/about/office-of-the-president",
    # administration
    "https://nemsu.edu.ph/administration/vpaf",
    "https://nemsu.edu.ph/administration/good-governance",
    "https://nemsu.edu.ph/administration/vppsi",
    # academics
    "https://nemsu.edu.ph/academics/academic-affairs",
    "https://nemsu.edu.ph/academics/academic-affairs/colleges/college-of-accountancy",
    "https://nemsu.edu.ph/academics/academic-affairs/colleges/college-of-agriculture-and-forestry",
    "https://nemsu.edu.ph/academics/academic-affairs/colleges/college-of-arts-and-sciences",
    "https://nemsu.edu.ph/academics/academic-affairs/colleges/college-of-business-and-management",
    "https://nemsu.edu.ph/academics/academic-affairs/colleges/college-of-criminal-justice-education",
    "https://nemsu.edu.ph/academics/academic-affairs/colleges/college-of-engineering-and-technology",
    "https://nemsu.edu.ph/academics/academic-affairs/colleges/college-of-fisheries-and-aquatic-sciences",
    "https://nemsu.edu.ph/academics/academic-affairs/colleges/college-of-information-technology-education",
    "https://nemsu.edu.ph/academics/academic-affairs/colleges/college-of-teacher-education",
    "https://nemsu.edu.ph/academics/academic-affairs/graduate-professional-studies/college-of-law",
    "https://nemsu.edu.ph/academics/academic-affairs/graduate-professional-studies/college-of-medicine",
    "https://nemsu.edu.ph/academics/academic-affairs/graduate-professional-studies/graduate-school",
    # research, innovation and extension (also holds the patents section)
    "https://nemsu.edu.ph/research-innovation-extension",
    "https://nemsu.edu.ph/research-innovation-extension/research-centers",
    "https://nemsu.edu.ph/research-innovation-extension/publications",
    # campuses
    "https://nemsu.edu.ph/campuses/tandag",
]