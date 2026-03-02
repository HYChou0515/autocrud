import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/autocrud-admin/pet-job/')({
  component: RouteComponent,
})

function RouteComponent() {
  return <div>Hello "/autocrud-admin/pet-job/"!</div>
}
