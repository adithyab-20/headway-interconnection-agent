import type { Metadata } from "next";
import { PageTransition } from "@/components/PageTransition";
import { SitePage } from "@/components/site/SitePage";

type Params = { params: Promise<{ site: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  return { title: decodeURIComponent((await params).site) };
}

export default async function Substation({ params }: Params) {
  return (
    <PageTransition>
      <SitePage site={decodeURIComponent((await params).site)} />
    </PageTransition>
  );
}
