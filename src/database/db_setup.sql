/* ============================================================
   staffing_allocation_v2 (Ingestion-First Architecture)

   Portfolio note:
   This schema is from a real production consulting project.
   Department names and institution-specific identifiers have
   been replaced with generic equivalents. All structural
   decisions, data types, and seed data reflect the actual
   production database.
   ============================================================ */

CREATE DATABASE IF NOT EXISTS staffing_allocation_v2;
USE staffing_allocation_v2;

-- Drop tables if they exist (fresh setup)
DROP TABLE IF EXISTS matched_applicants;
DROP TABLE IF EXISTS common_skills;
DROP TABLE IF EXISTS units;
DROP TABLE IF EXISTS applicants;
DROP TABLE IF EXISTS matching_batches;

/* ============================================================
   1. Matching Batches
      Tracks ingestion sessions so results from different
      upload cycles can be archived without data loss.
   ============================================================ */
CREATE TABLE matching_batches (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    batch_name  VARCHAR(255) NOT NULL,
    status      VARCHAR(50)  DEFAULT 'IN-PROGRESS', -- 'IN-PROGRESS', 'COMPLETED', 'ARCHIVED'
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP
);

/* ============================================================
   2. Applicants
      Core applicant record enhanced with a resume ingestion
      cache. Storing extracted resume text and a file hash
      allows the pipeline to skip re-extraction on unchanged
      files, cutting processing time significantly on large
      batches.
   ============================================================ */
CREATE TABLE applicants (
    id                   INT PRIMARY KEY AUTO_INCREMENT,
    applicant_id         VARCHAR(50)  UNIQUE NOT NULL,
    name                 VARCHAR(255) NOT NULL,
    name_source          VARCHAR(30)  NULL,
    gpa                  DECIMAL(3,2),
    program              VARCHAR(100),
    work_hours           INT,
    skills               JSON,
    matched_unit         VARCHAR(255),

    -- Resume ingestion cache ----------------------------------
    -- LONGTEXT stores full content of large resume files
    resume_text          LONGTEXT     NULL,
    -- SHA-256 hash lets the pipeline skip unchanged files
    file_hash            VARCHAR(64)  NULL,
    -- Extraction progress visible in the UI
    extraction_status    VARCHAR(20)  DEFAULT 'PENDING', -- PENDING | COMPLETED | FAILED
    extracted_at         DATETIME     NULL,
    batch_id             INT          NULL,
    -- ---------------------------------------------------------

    raw_skills_extracted TEXT         NULL,
    normalized_skills    TEXT         NULL,

    FOREIGN KEY (batch_id) REFERENCES matching_batches(id) ON DELETE SET NULL
);

/* ============================================================
   3. Units
      Business units / departments that applicants are matched
      to. Skills and preferred programs stored as JSON arrays
      so the admin can update them via the UI without schema
      changes. max_applicants enforces the vacancy cap the
      client sets before each matching cycle.
   ============================================================ */
CREATE TABLE units (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    name                VARCHAR(255) UNIQUE NOT NULL,
    unit_skills         JSON         NOT NULL,
    preferred_programs  JSON         DEFAULT NULL,
    max_applicants      INT          DEFAULT NULL,
    createdDateTime     DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updateDateTime      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

/* ============================================================
   4. Common Skills
      Baseline professional competencies evaluated for ALL
      applicants regardless of unit (~30% of matching score).
      Managed via the admin UI — no schema change needed to
      add or remove skills.
   ============================================================ */
CREATE TABLE common_skills (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    skill_name  VARCHAR(255) NOT NULL UNIQUE
);

/* ============================================================
   5. Matched Applicants
      Final output of each matching run. One record per
      applicant; UNIQUE KEY on applicant_id prevents duplicate
      placements across runs.
   ============================================================ */
CREATE TABLE matched_applicants (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    applicant_id        VARCHAR(50)   NOT NULL,
    applicant_name      VARCHAR(255),
    skills_matched      TEXT,
    program             VARCHAR(100),
    matched_unit        VARCHAR(255),
    work_experience     DECIMAL(3,2),
    gpa                 DECIMAL(3,2),
    award_amount        DECIMAL(10,2) DEFAULT 0.00,
    createdDateTime     DATETIME      DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_applicant (applicant_id)
);


/* ============================================================
   SEED DATA — Units
   19 business units seeded with skill requirements and
   preferred degree programs. Skill lists reflect real
   department requirements; unit names are generalized.
   ============================================================ */
INSERT INTO units (name, unit_skills, preferred_programs) VALUES

('FINANCIAL REPORTING UNIT',
 JSON_ARRAY('Accounting Standards','Financial Statement Preparation','Account Reconciliation',
            'Financial Reporting','Accounting Software','Audit & Compliance','Business Writing'),
 JSON_ARRAY('MS in Accounting','MS in Finance','MS in Business Analytics/MS in Accounting')),

('ENTREPRENEURSHIP & VENTURES UNIT',
 JSON_ARRAY('Entrepreneurship Experience','Marketing','Budgeting','Financial Planning',
            'Business Plan Development','Market Research','Business Strategy','CRM Software','Event Planning'),
 NULL),

('INNOVATION & CHANGE LEADERSHIP UNIT',
 JSON_ARRAY('Data Analysis','Marketing','Project Management Platforms','Content Creation',
            'Design Tools','Stakeholder Engagement','Report Writing & Presentation','Adobe'),
 JSON_ARRAY('MBA','MBA/MS in Marketing')),

('REAL ESTATE & ECONOMICS UNIT',
 JSON_ARRAY('Economics','Statistics','Financial Modeling','Real Estate Finance',
            'PropTech','Policy Analysis','Real Estate Valuation','GIS & Spatial Analysis'),
 NULL),

('GLOBAL PROGRAMS & STUDENT SERVICES UNIT',
 JSON_ARRAY('Marketing','Graphic Design','Content Creation','Website Design','Database Management',
            'Cultural Programming','Multilingual Communication','Translation & Interpretation','Adobe'),
 NULL),

('FINANCE UNIT',
 JSON_ARRAY('Financial Modeling','Valuation','Portfolio Analysis','Statistics','Bloomberg Terminal',
            'Investing','Capital Markets','Financial Accounting','Power BI'),
 JSON_ARRAY('MS in Accounting','MS in Finance')),

('GRADUATE PROGRAMS OFFICE',
 JSON_ARRAY('Qualtrics','Student Outreach','Google Workspace','Marketing Research',
            'Social Media Analytics','Database Management','Report Writing','Project Management Platforms'),
 JSON_ARRAY('MS in Marketing','MBA','MS in Business Analytics','MBA/MS in Marketing','MBA/MS in Business Analytics')),

('HEALTHCARE OPERATIONS UNIT',
 JSON_ARRAY('Statistics','Healthcare Standards & Compliance','Database Management','Project Management',
            'Tableau','Power BI','Budgeting & Resource Allocation','Business Process Improvement',
            'EHR Familiarity','Survey Tools'),
 JSON_ARRAY('Master of Healthcare Administration')),

('INFORMATION SYSTEMS & OPERATIONS UNIT',
 JSON_ARRAY('Python','R','Tableau','Power BI','Statistical Modeling & Forecasting','HTML','SAP','SQL',
            'Data Mining','Database Design & Management','Azure','AWS',
            'Business Process Modeling','Oracle','ERP'),
 JSON_ARRAY('MS in Business Analytics','MBA / MS in Business Analytics',
            'MS in Business Analytics/MS in Accounting')),

('PUBLIC SERVICE & POLICY UNIT',
 JSON_ARRAY('Publication Research','Government and Non-Profit Management','Database Management',
            'Event Management','Government Databases','Grant Writing','Qualtrics',
            'Google Forms','Public Policy'),
 JSON_ARRAY('Master of Public Administration','MBA')),

('INTERNATIONAL STUDENT PROGRAMS UNIT',
 JSON_ARRAY('Event Planning & Support','Student Engagement Tools','Slate','Marketing & Outreach',
            'Cross-Cultural Communication','Database Management','Survey Tools & Feedback Analysis',
            'Eventbrite','MS Teams','Adobe','Canva'),
 NULL),

('IT SERVICES UNIT',
 JSON_ARRAY('Technical Support','SQL','Network Administration','Cybersecurity','AWS',
            'IT Helpdesk & Ticketing Systems','Web Development','Python','HTML',
            'Software Development','Adobe','Data Science'),
 NULL),

('MANAGEMENT & ORGANIZATIONAL BEHAVIOR UNIT',
 JSON_ARRAY('Quantitative Research & Statistics','Literature Review','Academic Databases',
            'Project Management','Organizational Behavior','Case Studies'),
 JSON_ARRAY('MBA')),

('MARKETING UNIT',
 JSON_ARRAY('SPSS','Qualtrics','Marketing Analytics','Forecasting','Content Creation',
            'CRM Platforms','Digital Marketing','Advertising','Marketing Research',
            'Branding','Consumer Insights','Adobe Creative Suite','Canva'),
 JSON_ARRAY('MS in Marketing')),

('CIVIC ENGAGEMENT & PUBLIC AFFAIRS UNIT',
 JSON_ARRAY('Public Policy Knowledge','Event Planning','Outreach','Grant Writing & Management',
            'Public Administration','Policy Analysis','Academic Research','Survey Tools',
            'Municipal Databases'),
 JSON_ARRAY('Master of Public Administration','MBA')),

('POLICY & COMMUNITY PROGRAMS UNIT',
 JSON_ARRAY('Event Management','Quantitative Research & Statistics','Marketing','Public Policy',
            'Survey Tools','Grant & Proposal Writing/Management','Academic Research Databases'),
 JSON_ARRAY('Master of Public Administration','MBA','MS in Marketing')),

('GRADUATE ADMISSIONS UNIT',
 JSON_ARRAY('Slate','Salesforce','Digital Marketing','Event Coordination','Workflow Management',
            'Outreach','Data Analysis','Content Creation','Database Management','Canva','Adobe'),
 NULL),

('STRATEGY & INTERNATIONAL BUSINESS UNIT',
 JSON_ARRAY('Data Analysis','Cross-Cultural Communication','Global Markets & International Trade',
            'Management Strategy Analysis','Risk Analysis',
            'Market Entry & Competitive Analysis','Business Development'),
 JSON_ARRAY('MBA','MS in Marketing','MS in Finance','MBA/MS in Marketing')),

('UNDERGRADUATE PROGRAMS OFFICE',
 JSON_ARRAY('Qualtrics','Student Outreach','Google Workspace','Marketing Research',
            'Social Media Analytics','Database Management','Report Writing',
            'Project Management Platforms','Adobe'),
 NULL);


/* ============================================================
   SEED DATA — Common Skills
   28 baseline competencies evaluated across all applicants.
   ============================================================ */
INSERT IGNORE INTO common_skills (skill_name) VALUES
('ability to summarize information'),
('teamwork'),
('ability to work independently'),
('ability to work with different technology'),
('adaptability'),
('attention to detail'),
('written communication'),
('oral communication'),
('computer skills'),
('critical thinking'),
('MS Excel'),
('familiarity with AI tools and software'),
('interpersonal skills'),
('data collection and analytic software knowledge'),
('Microsoft Office Suite (Word, Excel, PowerPoint)'),
('multitasking'),
('problem solving'),
('professionalism & work ethic'),
('research'),
('self-starter'),
('speaking/presentation skills'),
('writing skills'),
('analyzing papers'),
('tutoring'),
('financial reporting'),
('customer service'),
('time management'),
('willingness to learn new technologies');
