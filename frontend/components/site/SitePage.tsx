"use client";

// A substation page: The odds, Ask and Write-up, over one project at one substation. The
// project, the comparison group and the projects left out are the page's own state; when a
// write-up exists, every change to what's counted is made to it too, so it stays in step.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Drawer, type HowWeKnow } from "@/components/Drawer";
import { api, ApiError, type Assessment, type Odds, type SiteDetail, type SiteSummary } from "@/shared/api";
import { Back, Chat } from "@/shared/icons";
import { Ask, type Msg, type Pending } from "./Ask";
import { Overview, type Project, type Tab } from "./Overview";
import { Writeup } from "./Writeup";
import { plainGroup } from "./words";

type View = "overview" | "ask" | "writeup";

const START_TYPE = "Solar + battery";
const START_MW = 200;

export function SitePage({ site }: { site: string }) {
  const [detail, setDetail] = useState<SiteDetail | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [odds, setOdds] = useState<Odds | null>(null);
  const [oddsError, setOddsError] = useState<string | null>(null);
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [years, setYears] = useState(10);
  const [group, setGroup] = useState<string | null>(null);
  const [leftOut, setLeftOut] = useState<string[]>([]);
  const [changes, setChanges] = useState<string[]>([]);
  const [view, setView] = useState<View>("overview");
  const [tab, setTab] = useState<Tab>("fared");
  const [about, setAbout] = useState<HowWeKnow | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [writing, setWriting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);

  useEffect(() => {
    api
      .sites()
      .then((s) => setSites(s.sites))
      .catch(() => setSites(null));
  }, []);

  useEffect(() => {
    let live = true;
    api
      .site(site, leftOut)
      .then((d) => {
        if (!live) return;
        setDetail(d);
        setProject(
          (p) =>
            p ?? {
              type: START_TYPE,
              mw: START_MW,
              place: (d.places.find((x) => x.voltage_kv === 230) ?? d.places[0]).place,
            },
        );
      })
      .catch((e: Error) => live && setFailed(e.message));
    return () => {
      live = false;
    };
  }, [site, leftOut]);

  useEffect(() => {
    if (!project) return;
    let live = true;
    setOddsError(null);
    api
      .odds({ place: project.place, projectType: project.type, mw: project.mw, years, group, leaveOut: leftOut })
      .then((o) => live && setOdds(o))
      .catch((e: Error) => {
        if (!live) return;
        setOdds(null);
        setOddsError(e.message);
      });
    return () => {
      live = false;
    };
  }, [project, years, group, leftOut]);

  const why = useCallback((a: HowWeKnow) => setAbout(a), []);
  const closeAbout = useCallback(() => setAbout(null), []);

  const ensureAssessment = useCallback(async (): Promise<Assessment | string> => {
    if (assessment) return assessment;
    if (!project) return "The page is still loading.";
    setWriting(true);
    setProblem(null);
    try {
      let made = await api.write(site, project.type, project.mw);
      // A write-up is about the same thing as the page: the same projects left out, and the
      // same comparison group where the write-up offers it.
      if (leftOut.length || group) {
        try {
          made = await api.adjust(made.id, {
            why: "Brought in line with the changes already made on the page",
            leave_out: leftOut,
            comparison_group: group,
          });
        } catch {
          // The assistant's lookups didn't offer the page's group: say so, rather than let
          // the write-up quietly compare with something else.
          made = await api.adjust(made.id, { why: "Brought in line with the page", leave_out: leftOut });
          setProblem(
            `The write-up couldn't use the comparison group chosen on the page (${plainGroup(group as string)}), so it compares with the group the assistant looked up.`,
          );
        }
      }
      setAssessment(made);
      return made;
    } catch (e) {
      const said = e instanceof ApiError ? e.message : `The write-up couldn't be made: ${(e as Error).message}`;
      setProblem(said);
      return said;
    } finally {
      setWriting(false);
    }
  }, [assessment, project, site, leftOut, group]);

  const change = useCallback(
    async (c: { leaveOut: string[]; group: string | null; why: string; inWriteup: boolean }): Promise<string | null> => {
      if (assessment && !c.inWriteup) {
        try {
          setAssessment(
            await api.adjust(assessment.id, {
              why: c.why || "No reason given",
              leave_out: c.leaveOut,
              comparison_group: c.group,
            }),
          );
        } catch (e) {
          return `The write-up couldn't take this change, so nothing was changed: ${(e as Error).message}`;
        }
      }
      if (c.leaveOut.length) {
        setLeftOut((was) => [...new Set([...was, ...c.leaveOut])].sort());
        setChanges((was) => [
          ...was,
          `Left out ${c.leaveOut.join(", ")}. Every number was worked out again${c.why ? `. Reason: "${c.why}"` : ""}.`,
        ]);
      }
      if (c.group) {
        setGroup(c.group);
        setChanges((was) => [...was, `Now comparing with ${plainGroup(c.group as string)}.`]);
      }
      return null;
    },
    [assessment],
  );

  const act = async (f: (id: string) => Promise<Assessment>) => {
    if (!assessment) return;
    setProblem(null);
    try {
      setAssessment(await f(assessment.id));
    } catch (e) {
      setProblem((e as Error).message);
    }
  };

  if (failed) {
    return (
      <div className="page">
        <Link className="link back" href="/map" transitionTypes={["page-back"]}>
          <Back /> All substations
        </Link>
        <p className="notice">This substation couldn&apos;t be loaded: {failed}</p>
      </div>
    );
  }
  if (!detail || !project) return <div className="page loading">Loading {site}…</div>;

  const toReview = assessment?.claims.filter((c) => c.kind === "judgement" && c.decision === "awaiting").length ?? 0;
  const kvs = detail.places.map((p) => p.voltage_kv).filter((v): v is number => v != null);
  const typeWords = project.type ? project.type.toLowerCase() : "project of any type";
  const projectLabel = `${project.mw} MW ${typeWords} at ${project.place}`;
  const where = detail.county ? `${detail.county} County` : "county not given";

  return (
    <div className="page">
      <Link className="link back" href="/map" transitionTypes={["page-back"]}>
        <Back /> All substations
      </Link>
      <div className="head">
        <div>
          <h1>{detail.site}</h1>
          <div className="sub">
            Substation in {where}
            {kvs.length ? ` · ${kvs.join(", ").replace(/, (\d+)$/, " and $1")} kV` : ""}
            {detail.positioned_by === "planned" ? " · planned, not built yet" : ""}
          </div>
        </div>
        <div className="views" role="tablist" aria-label="View">
          <button role="tab" aria-selected={view === "overview"} onClick={() => setView("overview")}>
            The odds
          </button>
          <button role="tab" aria-selected={view === "ask"} onClick={() => setView("ask")}>
            <Chat /> Ask
          </button>
          <button role="tab" aria-selected={view === "writeup"} onClick={() => setView("writeup")}>
            Write-up{toReview > 0 && !assessment?.final && <span className="badge">{toReview} to review</span>}
          </button>
        </div>
      </div>

      {view === "overview" && (
        <Overview
          detail={detail}
          odds={odds}
          oddsError={oddsError}
          sites={sites}
          project={project}
          setProject={(p) => {
            setGroup(null);
            setProject(p);
          }}
          years={years}
          setYears={setYears}
          group={group}
          setGroup={(g) => {
            if (!g) return;
            if (assessment) {
              // A write-up exists: propose the change in Ask, where it applies once confirmed.
              setView("ask");
              setPending({ group: g });
            } else void change({ leaveOut: [], group: g, why: `Compare with ${plainGroup(g)}`, inWriteup: false });
          }}
          tab={tab}
          setTab={setTab}
          why={why}
          askAbout={(q) => {
            setView("ask");
            setPending({ ask: q });
          }}
        />
      )}
      {view === "ask" && (
        <Ask
          site={detail.site}
          detail={detail}
          odds={odds}
          years={years}
          projectLabel={projectLabel}
          assessment={assessment}
          setAssessment={setAssessment}
          ensureAssessment={ensureAssessment}
          msgs={msgs}
          setMsgs={setMsgs}
          changes={changes}
          change={change}
          why={why}
          openTab={(t) => {
            setView("overview");
            setTab(t);
          }}
          openWriteup={() => setView("writeup")}
          pending={pending}
          clearPending={() => setPending(null)}
        />
      )}
      {view === "writeup" && (
        <Writeup
          site={detail.site}
          asOf={detail.as_of}
          assessment={assessment}
          writing={writing}
          problem={problem}
          write={() => void ensureAssessment()}
          why={why}
          openAsk={() => setView("ask")}
          decide={(id, d) => act((a) => api.decide(a, id, d))}
          reword={(id, text) => act((a) => api.reword(a, id, text))}
          finalise={() => act((a) => api.finalise(a))}
          pageProject={{ type: project.type, mw: project.mw }}
        />
      )}
      {about && <Drawer about={about} onClose={closeAbout} />}
    </div>
  );
}
