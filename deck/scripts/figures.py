#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""figures.py — Insighta 브랜드 고해상도 시각자료 생성기.
도형(Graphviz) · 차트(matplotlib) · 수식(mathtext) PNG를 만들어 PPTX에 임베딩한다.
academic-report-builder의 '자동 레이아웃 도형' 핵심을 브랜드 팔레트로 이식.

사용: python figures.py OUTDIR        # 데모 자산 일괄 생성
또는  from figures import *           # 개별 함수 호출
"""
import os, sys, subprocess
import graphviz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "..", "assets", "fonts")

# ---- Insighta 팔레트 ----
INK="#0F172A"; MUT="#475569"; FAINT="#94A3B8"; LINE="#CBD5E1"
PRIMARY="#2563EB"; PURPLE="#7C3AED"
CAT = {  # (main, tint, deep)
 "blue":("#2563EB","#EFF4FF","#1D4ED8"), "emerald":("#059669","#ECFDF5","#047857"),
 "violet":("#7C3AED","#F5F0FF","#6D28D9"), "amber":("#D97706","#FFF7ED","#B45309"),
 "rose":("#E11D48","#FFF1F4","#BE123C"), "slate":("#475569","#F1F5F9","#334155")}

def install_fonts():
    """Pretendard/JetBrains Mono를 matplotlib + fontconfig(graphviz)에 등록."""
    fonts = os.path.expanduser("~/.fonts"); os.makedirs(fonts, exist_ok=True)
    for f in os.listdir(FONT_DIR):
        if f.endswith(".ttf"):
            p=os.path.join(FONT_DIR,f)
            fm.fontManager.addfont(p)
            subprocess.run(["cp",p,fonts],check=False)
    subprocess.run(["fc-cache","-f",fonts],capture_output=True)
    matplotlib.rcParams["font.family"]="Pretendard"
    matplotlib.rcParams["axes.unicode_minus"]=False

# ============ Graphviz 도형 ============
def diagram_ml_taxonomy(out):
    """머신러닝 모델 분류 트리 (고해상도, 브랜드 컬러, 투명 배경)."""
    g = graphviz.Digraph("taxonomy", format="png")
    g.attr(rankdir="TB", bgcolor="transparent", pad="0.3", ranksep="0.55", nodesep="0.22", dpi="300")
    g.attr("node", shape="box", style="rounded,filled", fontname="Pretendard",
           fontsize="13", margin="0.16,0.10", penwidth="1.6", color=PRIMARY, fontcolor=INK)
    g.attr("edge", color="#94A3B8", penwidth="1.6", arrowsize="0.8")
    # root
    g.node("ml","머신러닝", fillcolor="#0B1220", fontcolor="white", color="#0B1220", fontsize="15")
    def grp(nid,label,key):
        c=CAT[key]; g.node(nid,label, fillcolor=c[1], color=c[0], fontcolor=c[2], fontsize="14")
    def leaf(nid,label,key):
        c=CAT[key]; g.node(nid,label, fillcolor="white", color=c[0], fontcolor=INK)
    grp("sup","지도학습","blue"); grp("uns","비지도학습","emerald"); grp("rl","강화학습","violet")
    g.edge("ml","sup"); g.edge("ml","uns"); g.edge("ml","rl")
    # 지도학습
    grp("reg","회귀","blue"); grp("clf","분류","blue")
    g.edge("sup","reg"); g.edge("sup","clf")
    for i,(t) in enumerate(["선형 회귀","로지스틱 회귀"]):
        leaf(f"r{i}",t,"blue"); g.edge("reg",f"r{i}")
    for i,(t) in enumerate(["SVM","의사결정 트리","랜덤 포레스트","나이브 베이즈"]):
        leaf(f"c{i}",t,"blue"); g.edge("clf",f"c{i}")
    # 비지도학습
    grp("clu","클러스터링","emerald"); grp("dim","차원축소","emerald")
    g.edge("uns","clu"); g.edge("uns","dim")
    for i,t in enumerate(["K-평균","계층적"]):
        leaf(f"k{i}",t,"emerald"); g.edge("clu",f"k{i}")
    leaf("pca","PCA","emerald"); g.edge("dim","pca")
    # 강화학습
    leaf("agent","에이전트–환경 보상 루프","violet"); g.edge("rl","agent")
    base = out[:-4] if out.endswith(".png") else out
    g.render(base, cleanup=True)
    return base+".png"

def diagram_transformer(out):
    """Transformer 데이터 흐름 (간단·고해상도)."""
    g = graphviz.Digraph("tf", format="png")
    g.attr(rankdir="LR", bgcolor="transparent", pad="0.25", ranksep="0.4", nodesep="0.3", dpi="300")
    g.attr("node", shape="box", style="rounded,filled", fontname="Pretendard",
           fontsize="13", margin="0.18,0.11", penwidth="1.6")
    g.attr("edge", color="#94A3B8", penwidth="1.6", arrowsize="0.8")
    c=CAT["violet"]
    seq=[("inp","입력 토큰 + 위치 인코딩","white"),
         ("att","Multi-Head Self-Attention",c[1]),
         ("ffn","Feed-Forward Network","white"),
         ("norm","Add & LayerNorm  (×N)",c[1]),
         ("out","출력 (다음 토큰 확률)","white")]
    for nid,lab,fc in seq:
        g.node(nid,lab, fillcolor=fc, color=c[0], fontcolor=(c[2] if fc!="white" else INK))
    for a,b in zip([s[0] for s in seq],[s[0] for s in seq][1:]):
        g.edge(a,b)
    base = out[:-4] if out.endswith(".png") else out
    g.render(base, cleanup=True); return base+".png"

# ============ matplotlib 차트 ============
def _clean_ax(ax):
    for sp in ["top","right"]: ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color(LINE); ax.spines["bottom"].set_color(LINE)
    ax.tick_params(colors=MUT, labelsize=11)

def chart_concept_counts(out):
    cats=["학습\n패러다임","모델\n계열","신경망\n구조","구성·\n최적화","평가·\n검증","데이터·\n수학"]
    vals=[6,6,7,6,7,9]; cols=[CAT[k][0] for k in ["blue","emerald","violet","amber","rose","slate"]]
    fig,ax=plt.subplots(figsize=(11.0,2.7),dpi=200); fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    bars=ax.bar(cats,vals,color=cols,width=0.62,zorder=3)
    for b,v in zip(bars,vals):
        ax.text(b.get_x()+b.get_width()/2, v+0.15, str(v), ha="center", va="bottom",
                fontsize=13, fontweight="bold", color=INK)
    ax.set_ylim(0,10.5); ax.set_yticks([]); _clean_ax(ax)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="x", length=0, labelsize=11.5)
    for lbl in ax.get_xticklabels(): lbl.set_color(INK)
    plt.tight_layout(pad=0.4); fig.savefig(out, transparent=True, bbox_inches="tight"); plt.close()
    return out

def chart_asr_cost(out):
    """다크 슬라이드용 — 흰 텍스트, 투명 배경. $/hour."""
    names=["Groq\nWhisper turbo","OpenAI\nWhisper","Google\nChirp 2.0"]; vals=[0.04,0.36,0.36]
    cols=["#A855F7","#475569","#475569"]
    fig,ax=plt.subplots(figsize=(8.0,3.0),dpi=200); fig.patch.set_alpha(0); ax.set_facecolor("none")
    bars=ax.barh(names[::-1],vals[::-1],color=cols[::-1],height=0.55,zorder=3)
    for b,v in zip(bars,vals[::-1]):
        ax.text(v+0.006, b.get_y()+b.get_height()/2, f"${v:.2f}/h", va="center", ha="left",
                fontsize=12, fontweight="bold", color="white")
    ax.set_xlim(0,0.44); ax.set_xticks([])
    for sp in ax.spines.values(): sp.set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=11.5, colors="white")
    for lbl in ax.get_yticklabels(): lbl.set_color("#E2E8F0")
    plt.tight_layout(pad=0.3); fig.savefig(out, transparent=True, bbox_inches="tight"); plt.close()
    return out

# ============ 수식 (mathtext) ============
def equation(out, latex, color=INK, fs=26):
    fig=plt.figure(figsize=(5.2,0.9),dpi=300); fig.patch.set_alpha(0)
    fig.text(0.01,0.5, f"${latex}$", fontsize=fs, color=color, va="center", ha="left")
    fig.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.06); plt.close()
    return out

EQUATIONS = [
 ("경사 하강법", r"\theta \leftarrow \theta - \eta\,\nabla_\theta J(\theta)"),
 ("평균제곱오차 (MSE)", r"\mathrm{MSE}=\frac{1}{n}\sum_{i=1}^{n}(y_i-\hat{y}_i)^2"),
 ("시그모이드", r"\sigma(x)=\frac{1}{1+e^{-x}}"),
 ("소프트맥스", r"\mathrm{softmax}(z_i)=\frac{e^{z_i}}{\sum_j e^{z_j}}"),
 ("베이즈 정리", r"P(A\mid B)=\frac{P(B\mid A)\,P(A)}{P(B)}"),
]

def generate_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    install_fonts()
    res={}
    res["taxonomy"]=diagram_ml_taxonomy(os.path.join(outdir,"fig_taxonomy.png"))
    res["transformer"]=diagram_transformer(os.path.join(outdir,"fig_transformer.png"))
    res["counts"]=chart_concept_counts(os.path.join(outdir,"chart_counts.png"))
    res["asr"]=chart_asr_cost(os.path.join(outdir,"chart_asr.png"))
    for i,(name,tex) in enumerate(EQUATIONS):
        res[f"eq{i}"]=equation(os.path.join(outdir,f"eq_{i}.png"), tex,
                               color=CAT[["blue","emerald","violet","amber","rose"][i]][2])
    return res

if __name__=="__main__":
    out = sys.argv[1] if len(sys.argv)>1 else "./figures_out"
    r=generate_all(out)
    r.update(generate_teaching(out))
    for k,v in r.items():
        from PIL import Image
        print(f"{k:12s} {os.path.basename(v):20s} {Image.open(v).size}")

# ============ 개념을 가르치는 고해상도 차트 (정보 전달용) ============
import numpy as np

def _ax(figsize=(5.6,3.6)):
    fig,ax=plt.subplots(figsize=figsize,dpi=200); fig.patch.set_alpha(0); ax.set_facecolor("none")
    for sp in ["top","right"]: ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color(LINE); ax.spines["bottom"].set_color(LINE)
    ax.tick_params(colors=MUT, labelsize=9)
    return fig,ax

def teach_regression(out):
    rng=np.random.default_rng(7); x=np.linspace(0,10,40); y=1.1*x+2+rng.normal(0,1.6,40)
    fig,ax=_ax()
    ax.scatter(x,y,s=26,color=CAT["emerald"][0],alpha=0.8,zorder=3,label="데이터")
    xs=np.array([0,10]); ax.plot(xs,1.1*xs+2,color=CAT["emerald"][2],lw=2.6,zorder=4,label="적합된 직선")
    for xi,yi in zip(x[::4],y[::4]): ax.plot([xi,xi],[yi,1.1*xi+2],color=FAINT,lw=0.9,zorder=2)
    ax.set_xlabel("입력 x",fontsize=10,color=INK); ax.set_ylabel("출력 y",fontsize=10,color=INK)
    ax.legend(frameon=False,fontsize=9,loc="upper left")
    ax.set_title("회귀: 잔차(세로선) 제곱합을 최소화하는 직선",fontsize=10.5,color=INK,pad=8)
    plt.tight_layout(pad=0.4); fig.savefig(out,transparent=True,bbox_inches="tight"); plt.close(); return out

def teach_activation(out):
    x=np.linspace(-6,6,200); fig,ax=_ax()
    ax.plot(x,1/(1+np.exp(-x)),color=CAT["violet"][0],lw=2.4,label="Sigmoid")
    ax.plot(x,np.tanh(x),color=CAT["blue"][0],lw=2.4,label="Tanh")
    ax.plot(x,np.maximum(0,x)/6,color=CAT["amber"][0],lw=2.4,label="ReLU (스케일)")
    ax.axhline(0,color=LINE,lw=0.8); ax.axvline(0,color=LINE,lw=0.8)
    ax.set_ylim(-1.2,1.2); ax.legend(frameon=False,fontsize=9,loc="lower right")
    ax.set_title("활성화 함수: 비선형성을 부여",fontsize=10.5,color=INK,pad=8)
    plt.tight_layout(pad=0.4); fig.savefig(out,transparent=True,bbox_inches="tight"); plt.close(); return out

def teach_gradient(out):
    x=np.linspace(-3,3,200); f=lambda t:t**2+1; fig,ax=_ax()
    ax.plot(x,f(x),color=BLUE if False else CAT["blue"][0],lw=2.4,zorder=2,label="손실 J(θ)")
    p=2.6
    for _ in range(6):
        ax.scatter(p,f(p),s=55,color=CAT["blue"][2],zorder=4)
        p2=p-0.45*(2*p)
        ax.annotate("",xy=(p2,f(p2)),xytext=(p,f(p)),arrowprops=dict(arrowstyle="->",color=CAT["rose"][0],lw=1.6))
        p=p2
    ax.scatter(0,f(0),s=80,color=CAT["emerald"][0],zorder=5,label="최소점")
    ax.set_xlabel("파라미터 θ",fontsize=10,color=INK); ax.set_ylabel("손실",fontsize=10,color=INK)
    ax.legend(frameon=False,fontsize=9,loc="upper center")
    ax.set_title("경사 하강: 기울기 반대로 내려가며 손실 최소화",fontsize=10.5,color=INK,pad=8)
    plt.tight_layout(pad=0.4); fig.savefig(out,transparent=True,bbox_inches="tight"); plt.close(); return out

def teach_overfit(out):
    e=np.linspace(1,30,30); fig,ax=_ax()
    train=2.2*np.exp(-e/8)+0.15
    val=2.2*np.exp(-e/8)+0.15+0.0016*(e-12)**2
    ax.plot(e,train,color=CAT["blue"][0],lw=2.4,label="훈련 오차")
    ax.plot(e,val,color=CAT["rose"][0],lw=2.4,label="검증 오차")
    k=int(np.argmin(val)); ax.scatter(e[k],val[k],s=70,color=CAT["emerald"][0],zorder=5)
    ax.annotate("최적 (조기 종료)",(e[k],val[k]),textcoords="offset points",xytext=(6,14),fontsize=9,color=CAT["emerald"][2])
    ax.axvspan(e[k],30,color=CAT["rose"][1],alpha=0.5); ax.text(24,1.4,"과적합",color=CAT["rose"][2],fontsize=9.5,ha="center")
    ax.set_xlabel("학습 반복(epoch)",fontsize=10,color=INK); ax.set_ylabel("오차",fontsize=10,color=INK)
    ax.legend(frameon=False,fontsize=9,loc="upper right")
    ax.set_title("과적합: 검증 오차가 다시 오르는 지점",fontsize=10.5,color=INK,pad=8)
    plt.tight_layout(pad=0.4); fig.savefig(out,transparent=True,bbox_inches="tight"); plt.close(); return out

def teach_roc(out):
    fpr=np.linspace(0,1,100); tpr=fpr**0.35; fig,ax=_ax(figsize=(5.0,3.8))
    ax.plot([0,1],[0,1],color=FAINT,lw=1.4,ls="--",label="랜덤 (AUC 0.5)")
    ax.plot(fpr,tpr,color=CAT["rose"][0],lw=2.6,label="모델 (AUC≈0.83)")
    ax.fill_between(fpr,fpr,tpr,color=CAT["rose"][1],alpha=0.6)
    ax.set_xlabel("거짓 양성률 (FPR)",fontsize=10,color=INK); ax.set_ylabel("참 양성률 (TPR)",fontsize=10,color=INK)
    ax.set_xlim(0,1); ax.set_ylim(0,1.02); ax.legend(frameon=False,fontsize=9,loc="lower right")
    ax.set_title("ROC 곡선: 곡선 아래 면적이 클수록 우수",fontsize=10.5,color=INK,pad=8)
    plt.tight_layout(pad=0.4); fig.savefig(out,transparent=True,bbox_inches="tight"); plt.close(); return out

def teach_kmeans(out):
    rng=np.random.default_rng(3); cols=[CAT["blue"][0],CAT["emerald"][0],CAT["amber"][0]]
    cents=[(2,2),(7,3),(4,7)]; fig,ax=_ax()
    for (cx,cy),c in zip(cents,cols):
        pts=rng.normal([cx,cy],0.7,(30,2)); ax.scatter(pts[:,0],pts[:,1],s=24,color=c,alpha=0.75,zorder=3)
        ax.scatter(cx,cy,marker="X",s=160,color="#0F172A",zorder=5,edgecolors="white",linewidths=1.5)
    ax.set_title("K-평균: 가장 가까운 중심(X)으로 군집 분할",fontsize=10.5,color=INK,pad=8)
    ax.set_xticks([]); ax.set_yticks([])
    plt.tight_layout(pad=0.4); fig.savefig(out,transparent=True,bbox_inches="tight"); plt.close(); return out

def generate_teaching(outdir):
    os.makedirs(outdir,exist_ok=True); install_fonts()
    r={}
    r["reg"]=teach_regression(os.path.join(outdir,"t_regression.png"))
    r["act"]=teach_activation(os.path.join(outdir,"t_activation.png"))
    r["grad"]=teach_gradient(os.path.join(outdir,"t_gradient.png"))
    r["over"]=teach_overfit(os.path.join(outdir,"t_overfit.png"))
    r["roc"]=teach_roc(os.path.join(outdir,"t_roc.png"))
    r["km"]=teach_kmeans(os.path.join(outdir,"t_kmeans.png"))
    return r
