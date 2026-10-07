import { Home } from "@/components/home/Home";
import { PageTransition } from "@/components/PageTransition";

export default function Page() {
  return (
    <PageTransition>
      <Home />
    </PageTransition>
  );
}
