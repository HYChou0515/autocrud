import { createFileRoute, Outlet, Link, useLocation, useNavigate } from '@tanstack/react-router';
import { AppShell, NavLink, Title, Group, ScrollArea, Text } from '@mantine/core';
import {
  getResourceNames,
  getResource,
  isAsyncCreateJob,
  isAsyncUpdateJob,
  getAsyncCreateJobChildren,
  getAsyncUpdateJobChildren,
  getStandaloneJobNames,
} from '@/specstar/lib/resources';
import { APP_TITLE, APP_LOGO } from '@/specstar/generated/branding';
import {
  IconHome,
  IconDatabase,
  IconDatabaseExport,
  IconArrowsTransferUp,
  IconPlayerPlay,
  IconRefresh,
  IconSettingsAutomation,
} from '@tabler/icons-react';

export const Route = createFileRoute('/specstar-admin')({
  component: SpecStarLayout,
});

function SpecStarLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const resourceNames = getResourceNames();
  const standaloneJobNames = getStandaloneJobNames();

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 240, breakpoint: 'sm' }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="xs">
            <img src={APP_LOGO} alt="" width={32} height={32} />
            <Title order={3}>{APP_TITLE}</Title>
            <Text size="xs" c="dimmed">
              Management Console
            </Text>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <AppShell.Section>
          <NavLink
            component={Link}
            to="/specstar-admin"
            label="Dashboard"
            leftSection={<IconHome size={18} />}
            active={location.pathname === '/specstar-admin'}
          />
        </AppShell.Section>
        <AppShell.Section grow component={ScrollArea}>
          <Text size="xs" fw={500} c="dimmed" px="sm" py="xs">
            Resources
          </Text>
          {resourceNames
            .filter(
              (name) =>
                !isAsyncCreateJob(name) &&
                !isAsyncUpdateJob(name) &&
                !standaloneJobNames.includes(name),
            )
            .map((name) => {
              const config = getResource(name)!;
              const createJobChildren = getAsyncCreateJobChildren(name);
              const updateJobChildren = getAsyncUpdateJobChildren(name);
              const allJobChildren = [...createJobChildren, ...updateJobChildren];
              const isActive =
                location.pathname === `/specstar-admin/${name}` ||
                location.pathname.startsWith(`/specstar-admin/${name}/`);
              const hasActiveChild = allJobChildren.some(
                (jn) =>
                  location.pathname === `/specstar-admin/${jn}` ||
                  location.pathname.startsWith(`/specstar-admin/${jn}/`),
              );

              if (allJobChildren.length > 0) {
                return (
                  <NavLink
                    key={name}
                    label={config.label}
                    leftSection={<IconDatabase size={16} />}
                    active={isActive}
                    defaultOpened={isActive || hasActiveChild}
                    onClick={() => navigate({ to: `/specstar-admin/${name}` })}
                  >
                    {createJobChildren.map((jn) => {
                      const jConfig = getResource(jn)!;
                      return (
                        <NavLink
                          key={jn}
                          component={Link}
                          to={`/specstar-admin/${jn}`}
                          label={jConfig.label}
                          leftSection={<IconPlayerPlay size={14} />}
                          active={
                            location.pathname === `/specstar-admin/${jn}` ||
                            location.pathname.startsWith(`/specstar-admin/${jn}/`)
                          }
                        />
                      );
                    })}
                    {updateJobChildren.map((jn) => {
                      const jConfig = getResource(jn)!;
                      return (
                        <NavLink
                          key={jn}
                          component={Link}
                          to={`/specstar-admin/${jn}`}
                          label={jConfig.label}
                          leftSection={<IconRefresh size={14} />}
                          active={
                            location.pathname === `/specstar-admin/${jn}` ||
                            location.pathname.startsWith(`/specstar-admin/${jn}/`)
                          }
                        />
                      );
                    })}
                  </NavLink>
                );
              }

              return (
                <NavLink
                  key={name}
                  component={Link}
                  to={`/specstar-admin/${name}`}
                  label={config.label}
                  leftSection={<IconDatabase size={16} />}
                  active={isActive}
                />
              );
            })}
          {standaloneJobNames.length > 0 && (
            <>
              <Text size="xs" fw={500} c="dimmed" px="sm" py="xs">
                Jobs
              </Text>
              {standaloneJobNames.map((name) => {
                const config = getResource(name)!;
                const isActive =
                  location.pathname === `/specstar-admin/${name}` ||
                  location.pathname.startsWith(`/specstar-admin/${name}/`);
                return (
                  <NavLink
                    key={name}
                    component={Link}
                    to={`/specstar-admin/${name}`}
                    label={config.label}
                    leftSection={<IconSettingsAutomation size={16} />}
                    active={isActive}
                  />
                );
              })}
            </>
          )}
        </AppShell.Section>
        <AppShell.Section>
          <Text size="xs" fw={500} c="dimmed" px="sm" py="xs">
            System
          </Text>
          <NavLink
            component={Link}
            to="/specstar-admin/backup"
            label="Backup & Restore"
            leftSection={<IconDatabaseExport size={16} />}
            active={location.pathname.startsWith('/specstar-admin/backup')}
          />
          <NavLink
            component={Link}
            to="/specstar-admin/migrate"
            label="Schema Migration"
            leftSection={<IconArrowsTransferUp size={16} />}
            active={location.pathname.startsWith('/specstar-admin/migrate')}
          />
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
