# Education CRM — Updated Technical Brief

> Official specification provided by the product owner on 2026-09-15 (English version as supplied).
> It takes precedence over earlier AI-generated plans. Explicit owner decisions are recorded in `docs/decisions.md`.

A system for monitoring and processing statistical data on the education of university and school students in IT areas.

## List of abbreviations

- **CRM system** (Customer Relationship Management) is specialized software that helps companies centralize and automate customer interaction processes at all stages — from first contact to repeat purchase.
- **152-FZ** — Federal Law No. 152-FZ of July 27, 2006 "On Personal Data".
- **FSTEC Order No. 117** — "Requirements for the Protection of Information contained in State information systems, other information systems of government agencies, state unitary enterprises, and government agencies."
- **LMS** — Learning Management System.
- **IT product** — software that helps students study in one or more IT fields at a university.
- **IT program** — a program that contains methodological materials and practice in the field in which it is written.
- **IT direction** — the direction in IT for training, for example DevOps, QA, etc.
- **Workflow** — a sequential algorithm of actions, automated and visualized in a CRM system.

## Relevance of the task

In accordance with the instructions of the Government of the Russian Federation on the development of human resources in information technology, and in fulfillment of tasks set within federal projects, work is underway to establish a system for monitoring the training of qualified IT specialists among university students and school students.

For an objective ranking of educational programs in IT areas, it is necessary to create a system for monitoring the training of the personnel reserve in IT areas. The ranking is based on the relevance of the program, which becomes apparent from statistical data: applications for training, the number of students, the number of parallel streams.

This system (hereinafter CRM) will allow monitoring interaction with educational institutions in order to acquire skills in working with digital tools in demand on the market. Based on them, students will be able to gain relevant competencies in various IT areas. The solution automates the process of interaction with each university in different educational programs, which will allow educational institutions to get the final result faster.

At the moment, interaction with a university follows this path (workflow):

1. search for contacts of the responsible person at the university;
2. communicating with them and clarifying the relevance of IT programs;
3. organization of a meeting with university representatives;
4. exchange of necessary documents for signing;
5. optional: correction of documents before signing;
6. signing of documents;
7. transfer of IT training materials, IT product licenses and documentation to the university;
8. support for the implementation of IT products at the university;
9. teacher training;
10. updating the IT curriculum, taking into account the teacher's training and the addition of an IT product;
11. conducting classes;
12. updating product documentation and training materials;
13. professional development of teachers;
14. control over the execution of each stage.

## Task description

Develop a system for monitoring interaction with educational institutions in order to acquire skills in working with digital tools in demand on the market.

The system will allow:

- visualizing the cycle of interaction with each university;
- monitoring the life-cycle path of each interaction with the university for all IT programs and IT products.

The goal of the service is to reduce the labor costs of employees of the RTK IT School for interaction with universities by automating the entire interaction path.

## Service requirements

Implement a CRM system that automates the process of interaction with the university, can integrate via API with third-party customer systems (an LMS and a website), and meets the security requirements of 152-FZ "On Personal Data" and FSTEC Order No. 117. The service must meet the following requirements.

IT products, IT directions, the list of universities and the list of those responsible should be catalogs stored in the system database, which can be updated by uploading through the system interface according to an agreed mapping of fields in xls, xlsx format.

Fields:

- University name
- Vendor
- Software
- Contract number
- Signing the license
- License validity period (one year)
- Transfer status
- Manager's full name
- Responsible persons from the University
- Comment

Generate reports on all existing interactions with universities for the selected period.

## Functional requirements

Working with data:

- filtering the output of data for a selected period by selected universities, IT areas, and IT products and those responsible for them;
- visualization when working with statistical data (charts, graphs in png, pdf formats);
- visualization of the user's way of interacting with the university, with the possibility of switching from status to status, adjusting the naming of statuses, and the user commenting when switching from status to status;
- the ability to attach files to statuses in png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx formats;
- the ability to generate reports for the selected period in xls, xlsx, pdf formats according to selected columns: name of the university, IT department, IT product, status of work with the university, responsible;
- use the API to collect information from the website and LMS for approved fields in JSON format, followed by adding it to an existing or new workflow;
- the ability to create and/or modify a workflow (the basic one is described by the 14 points above). Creativity and AI are allowed inside;
- compliance with information security requirements in accordance with 152-FZ "On Personal Data" and FSTEC Order No. 117;
- when requesting visualization of CRM reports, the user should receive a file in one of the following formats: xls, xlsx, pdf;
- the ability of the system to adjust and create new workflows;
- implementation of authorization via Keycloak;
- implementation of the role model:
  - **User** — works in the program interface with the data allowed within the rights after authorization;
  - **Supervisor** — works in the program interface with the data allowed within the rights after authorization; privileges are higher than those of the user; can change the responsible users for universities (change, delete, appoint);
  - **Administrator** — extended rights to implement additional settings and manage user rights, as well as to differentiate users by access to data;
- implementation of interaction with the service via the web interface;
- a cache of user actions should be provided.

## Non-functional requirements

- Response time when working in the interface should be no more than 1 second (for example, switching workflow status, adding a comment to a status, or changing the selection used to generate reports).
- When making changes to statuses or manipulating data in the interface, the page should not be reloaded or reset every time.
- Error codes should be provided if there are problems in the functionality of the application.
- The interface should be intuitive.
- The documentation (user's guide and system administrator's guide) should be written in accessible, understandable language and contain screenshots of interface elements. All documentation must be integrated into the platform.
- The system must withstand a load of 50 concurrent users.
- The system must withstand building at least 10 parallel reports of varying complexity.

The service user should be able to:

- work with the data;
- collect data from two API sources: the LMS and the Laravel CMS website (the API contract will be provided during discussions with the teams);
- generate reports on all existing interactions with universities for the selected period for selected universities, IT areas, and IT products and those responsible, in xls, xlsx, and pdf formats.

The service administrator must be able to manage, supplement, and adjust user rights, additional settings, and user restrictions based on visible information.

## Possible user path

1. The user reaches the login window.
2. The user logs in and gains access to the data they have access to.
3. Data can be filtered by universities, IT programs, IT products and the status of interaction on them.
4. The status of the current university, program, or product can be updated with a comment, adding files, and, if necessary, adjusting the workflow status.
5. A report can be created and downloaded for the selected period, responsible persons, IT programs, and IT products.

The target audience is employees of the RTK IT School.

## Roles in the system

- **User** — CAM (key account manager) = university managers (about 20).
- **Head (Supervisor)** — heads of university managers.
- **Platform administrator** — technical specialists of the RTK IT School.

## Data sources (access will be provided during the work)

- catalog: university name, IT department, IT product, responsible persons from the School and the university;
- LMS of the RTK IT School;
- website of the RTK IT School.

## Requirements for the solution

- Acceptable back-end: Java Spring Boot/Kotlin, Python, or Node.js; front-end: React. PostgreSQL may be used for databases.
- All methods necessary to use the solution must be available and described in detail through Swagger UI, together with a list of all libraries and components used.
- The solution should be a separate service that can become an independent information system.
- The solution should provide for generating the resulting JSON file, and for wrapping application components in Docker containers.
- Complex technical and logical details of the solution should be accompanied by comments.
- Accompanying documentation is a prerequisite. It should describe:
  - the data processing methods used;
  - conditions and restrictions within the solution;
  - detailed instructions for compilation, assembly, and installation;
  - functional and component architecture in Archi.
- The contractor must provide open, uncompiled source code written without obfuscation.
- The service must run on a Linux operating system (for example Ubuntu, CentOS, and others).
- Use of the service and the design of its results should, as a priority, meet regulatory legal acts and relevant state standards from the Set of Standards for Automated Systems:
  - Federal Law No. 149-FZ of 27.07.2006 "On Information, Information Technologies and Information Protection";
  - Federal Law No. 152-FZ of 27.07.2006 "On Personal Data".

## Presentation requirements

The presentation is provided in pptx or pdf format.

## UX/UI requirements

- All described operations should be performed in a user-friendly interface, understandable to the user, in a strict style.
- Interfaces should be accessible and user-friendly.
- The script and the user's path should be intuitive.
- Each interface element must solve a specific task and be present on the screen only if necessary to solve the user's tasks.
- The solution should be accessible and user-friendly in desktop and mobile versions. Tablets and other horizontally oriented devices can use the desktop browser version.

## Evaluation criteria

### Preliminary examination

- The team's approach: idea, originality, implementation method, technologies used.
- Technical elaboration: code quality; ability to integrate into other enterprise systems; speed of the solution.
- Effectiveness within the task: checking the operation of reports.
- Match to the task: completeness of the accompanying descriptive documentation.

### Final examination

- The team's approach: idea, originality, implementation method, technologies used.
- Technical elaboration: code quality; ability to integrate into the customer's other enterprise systems; speed of the solution.
- Effectiveness within the task:
  - correct reports;
  - correct data display and filtering;
  - workflow implementation and adjustment;
  - objectivity of diagrams (reliability assessed by visual sensitivity and data reflection);
  - speed and convenience of work.
- Match to the task (UX/UI): intuitive interface; logically connected blocks placed side by side; sufficient contrast between text and background; formatted, easy-to-read text.
- The team's performance at the pitch session.

## Requirements for submitting solutions on the platform

- Link to the source code repository.
- Link to the presentation.
- Link to the prototype: a working CRM with access to the developed web interface.
- Link to the accompanying documentation (.doc/.pdf).

## Resources

Data from open sources, as well as provided catalogs of data on IT products, IT areas, universities and those responsible.
