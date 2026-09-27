import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://exocortex.zone',
  integrations: [
    starlight({
      title: 'Exocortex',
      description: 'A personal knowledge OS that thinks while you sleep.',
      social: {
        github: 'https://github.com/hretheum/exocortex',
      },
      customCss: ['./src/styles/custom.css'],
      sidebar: [
        { label: 'Why Exocortex', link: '/why-exocortex' },
        { label: 'Use Cases', link: '/use-cases' },
        { label: 'FAQ', link: '/faq' },
        { label: 'Alternatives', link: '/alternatives' },
        { label: 'Roadmap', link: '/roadmap' },
        {
          label: 'Quickstarts',
          items: [
            { label: 'For Consultants', link: '/quickstart-consultant' },
            { label: 'For Developers', link: '/quickstart-developer' },
            { label: 'For Researchers', link: '/quickstart-researcher' },
          ],
        },
        {
          label: 'Getting Started',
          items: [
            { label: 'Quickstart', link: '/getting-started/quickstart' },
            { label: 'Configuration', link: '/getting-started/configuration' },
            { label: 'VPS / Bare Metal', link: '/getting-started/vps-bare-metal' },
            { label: 'Docker Deployment', link: '/getting-started/docker-deployment' },
          ],
        },
        {
          label: 'Guides',
          items: [
            { label: 'Writing a Plugin', link: '/guides/writing-a-plugin' },
            { label: 'MCP Tools Reference', link: '/guides/mcp-tools' },
          ],
        },
        {
          label: 'Architecture',
          items: [
            { label: 'Overview', link: '/architecture/overview' },
            { label: 'Wiki Compiler', link: '/architecture/wiki-compiler' },
            { label: 'Knowledge Layers', link: '/architecture/knowledge-architecture' },
            { label: 'Source Pipeline', link: '/architecture/source-pipeline-pattern' },
            { label: 'Module System', link: '/architecture/module-system' },
          ],
        },
        { label: 'Lessons Learned', link: '/lessons-learned' },
        {
          label: 'Legal',
          items: [{ label: 'License', link: '/legal/license' }],
        },
      ],
    }),
  ],
});
